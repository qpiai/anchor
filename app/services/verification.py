import pickle
import base64
import json
from typing import Dict, Any, List, Tuple
from z3 import *
from .rule_compiler import RuleCompiler
from .clarifying_questions import ClarifyingQuestionService
from ..models.schemas import VerificationResult

class VerificationService:
    def __init__(self):
        self.rule_compiler = RuleCompiler()
        self.clarifying_service = ClarifyingQuestionService()
    
    def _reconstruct_z3_objects(self, storage_data: Dict[str, Any]) -> Dict[str, Any]:
        """Reconstruct Z3 objects from stored policy data"""
        
        # If we have the original policy, recompile it fresh
        if 'original_policy' in storage_data:
            original_policy = storage_data['original_policy']
            # Create a fresh rule compiler instance and recompile
            fresh_compiler = RuleCompiler()
            return fresh_compiler.compile_policy(original_policy)
        
        # Fallback: try to work with serializable data (less reliable)
        serialized_policy = storage_data.get('serializable_data', storage_data)
        
        from z3 import String, Int, Bool, Solver, Not, And, Or, Implies, StringVal, IntVal, BoolVal
        
        # Recreate Z3 variables
        z3_vars = {}
        variable_info = serialized_policy['variables']
        
        for var_name, var_data in variable_info.items():
            if var_data['type'] == 'string' or var_data['type'] == 'enum':
                z3_vars[var_name] = String(var_name)
            elif var_data['type'] == 'number':
                z3_vars[var_name] = Int(var_name)
            elif var_data['type'] == 'boolean':
                z3_vars[var_name] = Bool(var_name)
        
        # Create placeholder rules (this is a fallback)
        reconstructed_rules = []
        for rule_data in serialized_policy['rules']:
            reconstructed_rules.append({
                'id': rule_data['id'],
                'description': rule_data['description'],
                'constraint': Bool(f"rule_{rule_data['id']}")  # Placeholder
            })
        
        # Create placeholder constraints
        reconstructed_constraints = []
        for constraint_str in serialized_policy['constraints']:
            reconstructed_constraints.append(Bool(f"constraint_{len(reconstructed_constraints)}"))
        
        return {
            'variables': z3_vars,
            'rules': reconstructed_rules,
            'constraints': reconstructed_constraints
        }
    
    def verify_scenario(self, extracted_variables: Dict[str, Any], z3_constraints: str, policy_rules: List[Dict]) -> Dict[str, Any]:
        """Use Z3 to verify extracted variables against compiled policies with comprehensive variable state handling"""
        
        try:
            # Check for missing mandatory variables first
            missing_mandatory = [var_name for var_name, var_value in extracted_variables.items() 
                               if var_value == "MISSING_MANDATORY"]
            
            if missing_mandatory:
                return {
                    'result': 'needs_clarification',
                    'rule_results': [],
                    'failed_rules': [],
                    'explanation': f"❓ Missing required information for: {', '.join(missing_mandatory)}",
                    'suggestions': self._generate_mandatory_questions(missing_mandatory),
                    'missing_mandatory_vars': missing_mandatory
                }
            
            # Deserialize base64-encoded policy data
            decoded_data = base64.b64decode(z3_constraints.encode('utf-8'))
            storage_data = pickle.loads(decoded_data)
            
            # Reconstruct Z3 objects from storage data
            reconstructed_policy = self._reconstruct_z3_objects(storage_data)
            
            # Filter out variables that should cause rule skipping
            effective_variables = {}
            skipped_variables = []
            
            for var_name, var_value in extracted_variables.items():
                if var_value == "SKIP_RULE":
                    skipped_variables.append(var_name)
                elif var_value != "MISSING_MANDATORY" and var_value is not None:  # Only valid values
                    effective_variables[var_name] = var_value
            
            # Create Z3 solver
            solver = Solver()
            
            # Add global constraints
            for constraint in reconstructed_policy['constraints']:
                solver.add(constraint)
            
            # Set variable values from effective variables only
            z3_vars = reconstructed_policy['variables']
            for var_name, var_value in effective_variables.items():
                if var_name in z3_vars:
                    z3_var = z3_vars[var_name]
                    try:
                        if isinstance(var_value, str):
                            solver.add(z3_var == StringVal(var_value))
                        elif isinstance(var_value, bool):
                            solver.add(z3_var == BoolVal(var_value))
                        elif isinstance(var_value, (int, float)):
                            if isinstance(var_value, float):
                                solver.add(z3_var == RealVal(var_value))
                            else:
                                solver.add(z3_var == IntVal(var_value))
                    except Exception as z3_error:
                        # Log and skip variables that cause Z3 errors
                        print(f"Warning: Skipping variable {var_name} due to Z3 error: {str(z3_error)}")
                        continue
            
            # Evaluate rules using a different approach:
            # We need to check if the current variable assignment satisfies all rules
            rule_results = []
            failed_rules = []
            
            # Create a complete model with all variable assignments
            all_constraints_solver = Solver()
            
            # Add all global constraints
            for constraint in reconstructed_policy['constraints']:
                all_constraints_solver.add(constraint)
            
            # Add all variable assignments (use effective_variables to avoid special markers)
            for var_name, var_value in effective_variables.items():
                if var_name in z3_vars:
                    z3_var = z3_vars[var_name]
                    try:
                        if isinstance(var_value, str):
                            all_constraints_solver.add(z3_var == StringVal(var_value))
                        elif isinstance(var_value, bool):
                            all_constraints_solver.add(z3_var == BoolVal(var_value))
                        elif isinstance(var_value, (int, float)):
                            if isinstance(var_value, float):
                                all_constraints_solver.add(z3_var == RealVal(var_value))
                            else:
                                all_constraints_solver.add(z3_var == IntVal(var_value))
                    except Exception as z3_error:
                        # Log and skip variables that cause Z3 errors
                        print(f"Warning: Skipping variable {var_name} in all_constraints_solver due to Z3 error: {str(z3_error)}")
                        continue
            
            # Evaluate each rule with rule skipping logic
            applicable_rules = []
            violated_rules = []
            supporting_rules = []
            skipped_rules = []
            
            for compiled_rule in reconstructed_policy['rules']:
                # Check if this rule depends on any skipped variables
                rule_uses_skipped_var = self._rule_depends_on_variables(compiled_rule, skipped_variables)
                
                if rule_uses_skipped_var:
                    # Skip this rule because it depends on optional variables with no defaults
                    skipped_rules.append(compiled_rule)
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'skipped',
                        'description': compiled_rule['description'],
                        'reason': f'Rule skipped due to unknown optional variables: {", ".join(skipped_variables)}'
                    })
                    continue
                
                all_constraints_solver.push()  # Save current state
                
                try:
                    # Check if the rule condition is satisfied by current variable assignments
                    all_constraints_solver.add(compiled_rule['constraint'])
                    condition_satisfied = all_constraints_solver.check() == sat
                except Exception as z3_error:
                    # Handle Z3 errors (like sort mismatch) gracefully
                    if "sort mismatch" in str(z3_error).lower():
                        # This rule likely depends on variables not properly handled
                        all_constraints_solver.pop()  # Restore state
                        skipped_rules.append(compiled_rule)
                        rule_results.append({
                            'rule_id': compiled_rule['id'],
                            'result': 'skipped',
                            'description': compiled_rule['description'],
                            'reason': f'Rule skipped due to Z3 constraint error: {str(z3_error)}'
                        })
                        continue
                    else:
                        # Re-raise other Z3 errors
                        all_constraints_solver.pop()  # Restore state
                        raise
                
                all_constraints_solver.pop()  # Restore state
                
                if condition_satisfied:
                    # Rule condition is TRUE - rule is applicable
                    applicable_rules.append(compiled_rule)
                    
                    if compiled_rule.get('conclusion') == 'valid':
                        # This rule supports validity
                        supporting_rules.append(compiled_rule)
                        rule_results.append({
                            'rule_id': compiled_rule['id'],
                            'result': 'pass',
                            'description': compiled_rule['description'],
                            'reason': 'Rule condition satisfied and supports validity'
                        })
                    elif compiled_rule.get('conclusion') == 'invalid':
                        # This rule indicates invalidity
                        violated_rules.append(compiled_rule)
                        failed_rules.append(compiled_rule)
                        rule_results.append({
                            'rule_id': compiled_rule['id'],
                            'result': 'fail',
                            'description': compiled_rule['description'],
                            'reason': 'Rule condition satisfied and indicates invalidity'
                        })
                else:
                    # Rule condition is FALSE - rule is not applicable
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'not_applicable',
                        'description': compiled_rule['description'],
                        'reason': 'Rule condition not satisfied, rule does not apply'
                    })
            
            # Enhanced result determination with rule skipping logic
            if len(effective_variables) == 0:
                # No effective variables - insufficient information
                overall_result = VerificationResult.NEEDS_CLARIFICATION
                explanation = "❓ Unable to extract sufficient information from the question and answer to evaluate the policy."
                
                # Use rule-based clarifying questions for now (LLM integration in API layer)
                suggestions = self.generate_clarifying_questions(applicable_rules, effective_variables, policy_rules)
            elif len(violated_rules) > 0:
                overall_result = VerificationResult.INVALID
                explanation = self.explain_verification_result(False, failed_rules)
                suggestions = self.generate_suggestions(failed_rules, effective_variables)
            elif len(supporting_rules) > 0:
                overall_result = VerificationResult.VALID
                explanation = self.explain_verification_result(True, [])
                suggestions = []
            else:
                # No rules apply - could be due to skipping or insufficient information
                if len(skipped_rules) > 0:
                    overall_result = VerificationResult.VALID  # Conservative approach - if no violating rules and some skipped, assume valid
                    explanation = f"✅ No policy violations found. {len(skipped_rules)} rule(s) were skipped due to insufficient optional information."
                    suggestions = []
                else:
                    overall_result = VerificationResult.NEEDS_CLARIFICATION
                    explanation = "❓ Unable to determine validity - no policy rules apply to this scenario based on the available information."
                    suggestions = self.generate_clarifying_questions(applicable_rules, effective_variables, policy_rules)
            
            # Add comprehensive rule summary to explanation
            total_rules = len(reconstructed_policy['rules'])
            active_rules = len(applicable_rules) + len(violated_rules)
            
            if len(skipped_rules) > 0 or active_rules < total_rules:
                explanation += f"\n\n📊 Rule Summary: {active_rules} active, {len(skipped_rules)} skipped, {total_rules - active_rules - len(skipped_rules)} not applicable"
            
            return {
                'result': overall_result.value if isinstance(overall_result, VerificationResult) else overall_result,
                'rule_results': rule_results,
                'failed_rules': [rule['id'] for rule in failed_rules],
                'explanation': explanation,
                'suggestions': suggestions
            }
            
        except Exception as e:
            return {
                'result': VerificationResult.ERROR.value,
                'rule_results': [],
                'failed_rules': [],
                'explanation': f"Verification failed: {str(e)}",
                'suggestions': []
            }
    
    def explain_verification_result(self, is_valid: bool, failed_rules: List[Dict]) -> str:
        """Generate human-readable explanation for verification result"""
        
        if is_valid:
            return "✅ All policy rules are satisfied. The scenario is valid according to the policy."
        else:
            explanation = "❌ The scenario violates the following policy rules:\n\n"
            
            for rule in failed_rules:
                explanation += f"• **{rule['id']}**: {rule['description']}\n"
            
            explanation += "\nPlease review the failed rules and adjust the scenario accordingly."
            
            return explanation
    
    def generate_suggestions(self, failed_rules: List[Dict], extracted_variables: Dict[str, Any]) -> List[str]:
        """Generate suggestions for making invalid scenarios valid"""
        
        suggestions = []
        
        for rule in failed_rules:
            rule_id = rule['id']
            description = rule['description']
            
            # Generate context-aware suggestions based on rule patterns
            if 'advance_notice' in rule_id.lower():
                suggestions.append("📅 Consider submitting the request earlier to meet advance notice requirements")
            
            elif 'approval' in rule_id.lower():
                suggestions.append("👤 Obtain manager approval before proceeding with the request")
            
            elif 'duration' in rule_id.lower() or 'days' in rule_id.lower():
                suggestions.append("⏱️ Consider reducing the duration or splitting into multiple shorter requests")
            
            elif 'emergency' in rule_id.lower():
                suggestions.append("🚨 Check if this qualifies as an emergency request with different requirements")
            
            elif 'eligibility' in rule_id.lower():
                suggestions.append("✅ Verify that all eligibility criteria are met before submitting")
            
            else:
                # Generic suggestion based on rule description
                suggestions.append(f"📋 Review the requirement: {description}")
        
        # Add general suggestions
        if len(failed_rules) > 1:
            suggestions.append("🔄 Consider breaking this into multiple separate requests")
            suggestions.append("📞 Contact HR or your manager for guidance on policy compliance")
        
        return suggestions
    
    def _rule_depends_on_variables(self, compiled_rule: Dict[str, Any], variable_names: List[str]) -> bool:
        """Check if a rule depends on any of the specified variables"""
        if not variable_names:
            return False
        
        # Get the original rule condition for more accurate dependency checking
        original_rule = compiled_rule.get('original_rule', {})
        condition = original_rule.get('condition', '')
        description = original_rule.get('description', '')
        
        # Check if any of the variable names appear in the condition
        rule_text = condition + " " + description
        
        for var_name in variable_names:
            # More precise matching - look for variable name as whole word
            import re
            if re.search(r'\b' + re.escape(var_name) + r'\b', rule_text):
                return True
        return False
    
    def _generate_mandatory_questions(self, missing_vars: List[str]) -> List[str]:
        """Generate questions for missing mandatory variables"""
        questions = []
        for var_name in missing_vars:
            questions.append(self._generate_variable_question(var_name))
        return questions[:3]  # Limit to 3 questions
    
    def generate_clarifying_questions(self, applicable_rules: List[Dict], extracted_variables: Dict[str, Any], policy_rules: List[Dict]) -> List[str]:
        """Generate clarifying questions when rules don't provide sufficient context - now focused on mandatory variables only"""
        questions = []
        
        # Priority 1: Check for mandatory variables that are missing (MISSING_MANDATORY marker)
        mandatory_missing = [var_name for var_name, var_value in extracted_variables.items() 
                           if var_value == "MISSING_MANDATORY"]
        
        if mandatory_missing:
            for var_name in mandatory_missing:
                question = self._generate_variable_question(var_name)
                if question:
                    questions.append(question)
            return questions[:3]  # Focus on mandatory variables only
        
        # Priority 2: If no mandatory missing but still need clarification, use generic questions
        # This should be rare with the new approach
        
        # If no specific variables identified, use generic questions based on context
        if not questions:
            if len(extracted_variables) > 0:
                # Have some variables but rules don't apply
                questions.extend([
                    "🔍 Are there any special circumstances or exceptions that might apply?",
                    "📋 Does this situation involve any specific procedures or requirements?",
                    "💼 What additional context would help evaluate this scenario?"
                ])
            else:
                # No variables extracted at all
                questions.extend([
                    "❓ Could you provide more specific details about this scenario?",
                    "📝 What are the key facts or conditions involved?", 
                    "🎯 What specific outcome or decision are you trying to verify?"
                ])
        
        return questions[:3]  # Limit to 3 questions to avoid overwhelming
    
    def _generate_variable_question(self, var_name: str) -> str:
        """Generate a clarifying question for a specific variable based on its name"""
        var_lower = var_name.lower()
        
        # Employment-related variables
        if 'employee' in var_lower or 'worker' in var_lower:
            if 'type' in var_lower:
                return f"👤 What type of {var_name.replace('_', ' ')} is this?"
            else:
                return f"👤 Could you specify the {var_name.replace('_', ' ')}?"
        
        # Time-related variables
        if any(time_word in var_lower for time_word in ['days', 'hours', 'weeks', 'months', 'duration', 'time']):
            return f"📅 What is the {var_name.replace('_', ' ')}?"
        
        # Approval/permission variables
        if any(approval_word in var_lower for approval_word in ['approval', 'permission', 'authorized', 'approved']):
            return f"✅ Is there {var_name.replace('_', ' ')} for this request?"
        
        # Amount/quantity variables
        if any(amount_word in var_lower for amount_word in ['amount', 'cost', 'budget', 'quantity', 'number']):
            return f"💰 What is the {var_name.replace('_', ' ')}?"
        
        # Status variables
        if 'status' in var_lower or 'state' in var_lower:
            return f"📊 What is the current {var_name.replace('_', ' ')}?"
        
        # Generic question
        return f"❓ Could you specify the {var_name.replace('_', ' ')}?"
    
    def compile_and_verify(self, policy_dict: Dict[str, Any], question: str, answer: str, extracted_variables: Dict[str, Any]) -> Dict[str, Any]:
        """Compile policy and verify in one step (for testing/development)"""
        
        try:
            # Compile the policy
            compiled_policy = self.rule_compiler.compile_policy(policy_dict)
            
            # Create storage data structure
            storage_data = {
                'serializable_data': compiled_policy['serializable_data'],
                'original_policy': policy_dict
            }
            # Serialize for storage (simulate database storage) using base64
            serialized_constraints = base64.b64encode(pickle.dumps(storage_data)).decode('utf-8')
            
            # Extract policy rules for context
            policy_rules = policy_dict.get('rules', [])
            
            # Verify the scenario
            result = self.verify_scenario(extracted_variables, serialized_constraints, policy_rules)
            
            return result
            
        except Exception as e:
            return {
                'result': VerificationResult.ERROR.value,
                'rule_results': [],
                'failed_rules': [],
                'explanation': f"Compilation or verification failed: {str(e)}",
                'suggestions': []
            }

# Example usage for testing
def test_verification():
    """Test the verification service with a sample policy"""
    
    policy_yaml = """
policy_name: "vacation_request_policy"
domain: "hr"
version: "1.0"

variables:
  - name: "advance_notice_days"
    type: "number"
    description: "Days between request submission and vacation start"
  - name: "vacation_duration_days"
    type: "number" 
    description: "Total consecutive days of vacation requested"
  - name: "request_type"
    type: "enum"
    possible_values: ["regular_vacation", "emergency_leave"]
    description: "Type of leave request"
  - name: "has_manager_approval"
    type: "boolean"
    description: "Whether request has manager approval"

rules:
  - id: "advance_notice_rule"
    condition: "request_type == 'regular_vacation' AND advance_notice_days < 14"
    conclusion: "invalid"
    description: "Regular vacation needs 2+ weeks advance notice"
  - id: "manager_approval_rule"  
    condition: "vacation_duration_days > 5 AND NOT has_manager_approval"
    conclusion: "invalid"
    description: "Long vacations need manager approval"
  - id: "emergency_exception_rule"
    condition: "request_type == 'emergency_leave'"
    conclusion: "valid"
    description: "Emergency leave bypasses normal rules"

constraints:
  - "advance_notice_days >= 0"
  - "vacation_duration_days > 0"
"""
    
    # Test scenarios
    test_scenarios = [
        {
            'name': 'Valid regular vacation',
            'variables': {
                'advance_notice_days': 20,
                'vacation_duration_days': 3,
                'request_type': 'regular_vacation',
                'has_manager_approval': False
            }
        },
        {
            'name': 'Invalid - insufficient notice',
            'variables': {
                'advance_notice_days': 5,
                'vacation_duration_days': 3,
                'request_type': 'regular_vacation',
                'has_manager_approval': False
            }
        },
        {
            'name': 'Invalid - long vacation without approval',
            'variables': {
                'advance_notice_days': 20,
                'vacation_duration_days': 10,
                'request_type': 'regular_vacation',
                'has_manager_approval': False
            }
        },
        {
            'name': 'Valid emergency leave',
            'variables': {
                'advance_notice_days': 0,
                'vacation_duration_days': 3,
                'request_type': 'emergency_leave',
                'has_manager_approval': False
            }
        }
    ]
    
    verification_service = VerificationService()
    
    print("=== Verification Test Results ===\n")
    
    for scenario in test_scenarios:
        print(f"Testing: {scenario['name']}")
        result = verification_service.compile_and_verify(
            policy_yaml, 
            "Test question",
            "Test answer", 
            scenario['variables']
        )
        
        print(f"Result: {result['result']}")
        print(f"Failed rules: {result['failed_rules']}")
        print(f"Explanation: {result['explanation']}")
        if result['suggestions']:
            print(f"Suggestions: {result['suggestions']}")
        print("-" * 50)

if __name__ == "__main__":
    test_verification() 