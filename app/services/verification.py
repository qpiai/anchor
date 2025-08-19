import pickle
import json
from typing import Dict, Any, List, Tuple
from z3 import *
from .rule_compiler import RuleCompiler

class VerificationService:
    def __init__(self):
        self.rule_compiler = RuleCompiler()
    
    def verify_scenario(self, extracted_variables: Dict[str, Any], z3_constraints: str, policy_rules: List[Dict]) -> Dict[str, Any]:
        """Use Z3 to verify extracted variables against compiled policies"""
        
        try:
            # Deserialize Z3 constraints
            compiled_policy = pickle.loads(z3_constraints.encode('latin-1'))
            
            # Create Z3 solver
            solver = Solver()
            
            # Add global constraints
            for constraint in compiled_policy['constraints']:
                solver.add(constraint)
            
            # Set variable values from extracted variables
            z3_vars = compiled_policy['variables']
            for var_name, var_value in extracted_variables.items():
                if var_name in z3_vars:
                    z3_var = z3_vars[var_name]
                    if isinstance(var_value, str):
                        solver.add(z3_var == StringVal(var_value))
                    elif isinstance(var_value, bool):
                        solver.add(z3_var == BoolVal(var_value))
                    elif isinstance(var_value, (int, float)):
                        if isinstance(var_value, float):
                            solver.add(z3_var == RealVal(var_value))
                        else:
                            solver.add(z3_var == IntVal(var_value))
            
            # Check each rule
            rule_results = []
            failed_rules = []
            
            for compiled_rule in compiled_policy['rules']:
                solver.push()  # Save current state
                
                # Try to violate the rule (add negation of the rule)
                solver.add(Not(compiled_rule['constraint']))
                
                if solver.check() == unsat:
                    # Rule cannot be violated, so it passes
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'pass',
                        'description': compiled_rule['description']
                    })
                else:
                    # Rule can be violated, so it fails
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'fail',
                        'description': compiled_rule['description']
                    })
                    failed_rules.append(compiled_rule)
                
                solver.pop()  # Restore state
            
            # Determine overall result
            overall_result = "valid" if len(failed_rules) == 0 else "invalid"
            
            # Generate explanation
            explanation = self.explain_verification_result(overall_result == "valid", failed_rules)
            
            # Generate suggestions for failed rules
            suggestions = self.generate_suggestions(failed_rules, extracted_variables) if failed_rules else []
            
            return {
                'result': overall_result,
                'rule_results': rule_results,
                'failed_rules': [rule['id'] for rule in failed_rules],
                'explanation': explanation,
                'suggestions': suggestions
            }
            
        except Exception as e:
            return {
                'result': 'error',
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
    
    def compile_and_verify(self, policy_yaml: str, question: str, answer: str, extracted_variables: Dict[str, Any]) -> Dict[str, Any]:
        """Compile policy and verify in one step (for testing/development)"""
        
        try:
            # Compile the policy
            compiled_policy = self.rule_compiler.compile_policy(policy_yaml)
            
            # Serialize for storage (simulate database storage)
            serialized_constraints = pickle.dumps(compiled_policy).decode('latin-1')
            
            # Extract policy rules from YAML for context
            import yaml
            policy_dict = yaml.safe_load(policy_yaml)
            policy_rules = policy_dict.get('rules', [])
            
            # Verify the scenario
            result = self.verify_scenario(extracted_variables, serialized_constraints, policy_rules)
            
            return result
            
        except Exception as e:
            return {
                'result': 'error',
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