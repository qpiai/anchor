import logging
import re
from typing import Dict, Any, List, Tuple
from z3 import *
from .compiled_store import dumps_compilation, get_compiled, resolve_stored_policy
from .rule_compiler import RuleCompiler
from .clarifying_questions import ClarifyingQuestionService
from ..models.schemas import VerificationResult

logger = logging.getLogger(__name__)

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
                z3_vars[var_name] = Real(var_name)
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
    
    def verify_scenario(
        self,
        extracted_variables: Dict[str, Any],
        z3_constraints: str,
        policy_rules: List[Dict],
        compilation_id: str | None = None,
        fallback_policy: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Verify extracted variables against a compiled policy.

        Precedence, first match wins:
        1. A global constraint already violated by the known facts is INVALID.
           The failed entry is named with that constraint. Asking for more
           facts cannot repair a value that is already impossible.
        2. An invalid-concluding rule already satisfied by the known facts is
           INVALID, even if other mandatory variables are missing. INVALID is
           the safer answer when the violation does not depend on those
           missing variables. If every invalid rule still depends on a missing
           variable, the result is NEEDS_CLARIFICATION instead.
        3. Any remaining missing mandatory variable is NEEDS_CLARIFICATION
           and lists missing_mandatory_vars.
        4. VALID requires positive permission: at least one valid-concluding
           rule is satisfied, and no invalid-concluding rule is satisfied.
           A skipped rule (optional variable with no default) is not permission.
        5. If nothing fires, the result is NEEDS_CLARIFICATION with
           uncovered=true and the explanation
           "No policy rule covers this case; route to human review."
        """

        try:
            missing_mandatory = [var_name for var_name, var_value in extracted_variables.items()
                               if var_value == "MISSING_MANDATORY"]

            policy_dict = resolve_stored_policy(z3_constraints, fallback_policy)
            reconstructed_policy = get_compiled(
                str(compilation_id) if compilation_id else None,
                policy_dict,
            )

            effective_variables = {}
            skipped_variables = []
            for var_name, var_value in extracted_variables.items():
                if var_value == "SKIP_RULE":
                    skipped_variables.append(var_name)
                elif var_value != "MISSING_MANDATORY" and var_value is not None:
                    effective_variables[var_name] = var_value

            z3_vars = reconstructed_policy['variables']
            constraint_labels = list(policy_dict.get('constraints') or [])
            violated_constraints = self._violated_constraints(
                z3_vars,
                reconstructed_policy['constraints'],
                constraint_labels,
                effective_variables,
            )
            if violated_constraints:
                failed_rules = [
                    {
                        'id': label,
                        'description': f"Global constraint violated: {label}",
                    }
                    for label in violated_constraints
                ]
                rule_results = [
                    {
                        'rule_id': label,
                        'result': 'fail',
                        'description': f"Global constraint violated: {label}",
                        'reason': 'Global constraint violated',
                    }
                    for label in violated_constraints
                ]
                return {
                    'result': VerificationResult.INVALID.value,
                    'rule_results': rule_results,
                    'failed_rules': [rule['id'] for rule in failed_rules],
                    'explanation': self.explain_verification_result(False, failed_rules),
                    'suggestions': self.generate_suggestions(failed_rules, effective_variables),
                }

            rule_results = []
            failed_rules = []
            applicable_rules = []
            violated_rules = []
            supporting_rules = []
            skipped_rules = []
            open_denies: List[str] = []   # unknown facts that could still trigger a deny rule
            open_permits: List[str] = []  # unknown facts that could still grant permission
            unknown_variables = skipped_variables + missing_mandatory

            # Only numeric range constraints ("leave_days > 0") may be assumed about unknown facts.
            # Anything else ("leave_days <= 30 OR has_manager_approval == true", 'method == "email"')
            # is a business rule: assuming it would fill an unknown fact with the compliant value.
            numeric = {name for name, var in z3_vars.items() if var.sort() in (RealSort(), IntSort())}
            solver = Solver()
            policy_constraints = []
            for index, constraint in enumerate(reconstructed_policy['constraints']):
                label = constraint_labels[index] if index < len(constraint_labels) else f"constraint_{index}"
                if self._is_range_constraint(label, numeric):
                    solver.add(constraint)
                else:
                    policy_constraints.append((label, constraint))
            self._add_assignments(solver, z3_vars, effective_variables)

            # Three-valued rule evaluation over the unknown facts:
            #   must fire  -> the rule applies whatever the unknowns are
            #   can't fire -> the rule never applies, so its unknowns do not matter
            #   may fire   -> the answer depends on an unknown fact
            for compiled_rule in reconstructed_policy['rules']:
                conclusion = str(compiled_rule.get('conclusion') or '').lower()
                unknown_here = [
                    name for name in unknown_variables
                    if self._rule_depends_on_variables(compiled_rule, [name])
                ]
                try:
                    can_fire = self._holds(solver, compiled_rule['constraint'])
                    must_fire = can_fire and not self._holds(solver, Not(compiled_rule['constraint']))
                except Exception as z3_error:
                    # An unevaluable deny rule must not silently allow: treat it as undecided.
                    skipped_rules.append(compiled_rule)
                    if conclusion == 'invalid':
                        open_denies.extend(unknown_here or ["__rule_error__"])
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'skipped',
                        'description': compiled_rule['description'],
                        'reason': f'Rule skipped due to Z3 constraint error: {str(z3_error)}'
                    })
                    continue

                if must_fire and conclusion == 'valid':
                    applicable_rules.append(compiled_rule)
                    supporting_rules.append(compiled_rule)
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'pass',
                        'description': compiled_rule['description'],
                        'reason': 'Rule condition satisfied and supports validity'
                    })
                elif must_fire and conclusion == 'invalid':
                    applicable_rules.append(compiled_rule)
                    violated_rules.append(compiled_rule)
                    failed_rules.append(compiled_rule)
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'fail',
                        'description': compiled_rule['description'],
                        'reason': 'Rule condition satisfied and indicates invalidity'
                    })
                elif can_fire:
                    skipped_rules.append(compiled_rule)
                    (open_denies if conclusion == 'invalid' else open_permits).extend(unknown_here)
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'skipped',
                        'description': compiled_rule['description'],
                        'reason': f'Depends on unknown facts: {", ".join(unknown_here) or "unknown"}',
                    })
                else:
                    rule_results.append({
                        'rule_id': compiled_rule['id'],
                        'result': 'not_applicable',
                        'description': compiled_rule['description'],
                        'reason': 'Rule condition not satisfied, rule does not apply'
                    })

            for label, constraint in policy_constraints:
                # Already-violated constraints returned INVALID above; here only "may be violated".
                try:
                    may_break = self._holds(solver, Not(constraint))
                except Exception:
                    may_break = True
                if may_break:
                    unknown_here = [name for name in unknown_variables
                                    if re.search(r'\b' + re.escape(name) + r'\b', label)]
                    open_denies.extend(unknown_here or ["__rule_error__"])
                    rule_results.append({
                        'rule_id': label,
                        'result': 'skipped',
                        'description': f"Global constraint: {label}",
                        'reason': f'Depends on unknown facts: {", ".join(unknown_here) or "unknown"}',
                    })

            def _needed(*groups: List[str]) -> List[str]:
                seen: List[str] = []
                for group in groups:
                    for name in group:
                        if name not in seen and name != "__rule_error__":
                            seen.append(name)
                return seen

            if violated_rules:
                overall_result = VerificationResult.INVALID
                explanation = self.explain_verification_result(False, failed_rules)
                suggestions = self.generate_suggestions(failed_rules, effective_variables)
                extra = {}
            elif missing_mandatory or open_denies:
                # A deny rule that may still fire blocks approval, even when its unknown fact is optional.
                needed = _needed(missing_mandatory, open_denies)
                overall_result = VerificationResult.NEEDS_CLARIFICATION
                if needed:
                    explanation = f"Missing required information for: {', '.join(needed)}"
                else:
                    explanation = "A policy rule could not be evaluated; route to human review."
                suggestions = self._generate_mandatory_questions(needed)
                extra = {'missing_mandatory_vars': needed}
            elif supporting_rules:
                overall_result = VerificationResult.VALID
                explanation = self.explain_verification_result(True, [])
                suggestions = []
                extra = {}
            elif open_permits:
                needed = _needed(open_permits)
                overall_result = VerificationResult.NEEDS_CLARIFICATION
                explanation = f"Missing required information for: {', '.join(needed)}"
                suggestions = self._generate_mandatory_questions(needed)
                extra = {'missing_mandatory_vars': needed}
            else:
                overall_result = VerificationResult.NEEDS_CLARIFICATION
                explanation = "No policy rule covers this case; route to human review."
                suggestions = self.generate_clarifying_questions(applicable_rules, effective_variables, policy_rules)
                extra = {'uncovered': True}

            if overall_result != VerificationResult.NEEDS_CLARIFICATION or 'uncovered' not in extra:
                if overall_result != VerificationResult.NEEDS_CLARIFICATION or not extra.get('missing_mandatory_vars'):
                    total_rules = len(reconstructed_policy['rules'])
                    active_rules = len(applicable_rules)
                    if skipped_rules or active_rules < total_rules:
                        explanation += (
                            f"\n\nRule Summary: {active_rules} active, {len(skipped_rules)} skipped, "
                            f"{total_rules - active_rules - len(skipped_rules)} not applicable"
                        )

            return {
                'result': overall_result.value,
                'rule_results': rule_results,
                'failed_rules': [rule['id'] for rule in failed_rules],
                'explanation': explanation,
                'suggestions': suggestions,
                **extra,
            }
            
        except Exception as e:
            return {
                'result': VerificationResult.ERROR.value,
                'rule_results': [],
                'failed_rules': [],
                'explanation': f"Verification failed: {str(e)}",
                'suggestions': []
            }

    def _add_assignments(self, solver, z3_vars: Dict[str, Any], variables: Dict[str, Any]) -> None:
        """Bind known values. Number variables are Reals, including integers."""
        for var_name, var_value in variables.items():
            if var_name not in z3_vars:
                continue
            z3_var = z3_vars[var_name]
            try:
                if isinstance(var_value, bool):
                    solver.add(z3_var == BoolVal(var_value))
                elif isinstance(var_value, str):
                    solver.add(z3_var == StringVal(var_value))
                elif isinstance(var_value, (int, float)):
                    if z3_var.sort() == RealSort():
                        solver.add(z3_var == RealVal(str(var_value)))
                    else:
                        solver.add(z3_var == IntVal(int(var_value)))
            except Exception as z3_error:
                print(f"Warning: Skipping variable {var_name} due to Z3 error: {str(z3_error)}")

    @staticmethod
    def _is_range_constraint(label: str, numeric: set) -> bool:
        """`x > 0`, `hours <= 24`: one numeric variable against a number."""
        match = re.fullmatch(r"\s*(\w+)\s*(>=|<=|>|<)\s*-?\d+(?:\.\d+)?\s*", str(label))
        return bool(match) and match.group(1) in numeric

    @staticmethod
    def _holds(solver, condition) -> bool:
        """True when `condition` is satisfiable together with the known facts."""
        solver.push()
        try:
            solver.add(condition)
            return solver.check() == sat
        finally:
            solver.pop()

    def _violated_constraints(self, z3_vars, constraints, labels, variables) -> List[str]:
        """Return original constraint texts already falsified by known facts."""
        violated = []
        for index, constraint in enumerate(constraints):
            label = labels[index] if index < len(labels) else f"constraint_{index}"
            solver = Solver()
            self._add_assignments(solver, z3_vars, variables)
            try:
                solver.add(constraint)
                if solver.check() == unsat:
                    violated.append(label)
            except Exception:
                continue
        return violated
    
    def explain_verification_result(self, is_valid: bool, failed_rules: List[Dict]) -> str:
        """Generate human-readable explanation for verification result"""
        
        if is_valid:
            return "All policy rules are satisfied. The scenario is valid according to the policy."
        else:
            explanation = "The scenario violates the following policy rules:\n\n"
            
            for rule in failed_rules:
                # The condition is what Z3 checked; the description is model-written and can drift.
                condition = (rule.get('original_rule') or {}).get('condition')
                suffix = f" (rule: `{condition}`)" if condition else ""
                explanation += f"- **{rule['id']}**: {rule['description']}{suffix}\n"
            
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
                suggestions.append("Consider submitting the request earlier to meet advance notice requirements")
            
            elif 'approval' in rule_id.lower():
                suggestions.append("Obtain manager approval before proceeding with the request")
            
            elif 'duration' in rule_id.lower() or 'days' in rule_id.lower():
                suggestions.append("Consider reducing the duration or splitting into multiple shorter requests")
            
            elif 'emergency' in rule_id.lower():
                suggestions.append("Check if this qualifies as an emergency request with different requirements")
            
            elif 'eligibility' in rule_id.lower():
                suggestions.append("Verify that all eligibility criteria are met before submitting")
            
            else:
                # Generic suggestion based on rule description
                suggestions.append(f"Review the requirement: {description}")
        
        # Add general suggestions
        if len(failed_rules) > 1:
            suggestions.append("Consider breaking this into multiple separate requests")
            suggestions.append("Contact HR or your manager for guidance on policy compliance")
        
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
        return questions
    
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
            return questions
        
        # Priority 2: If no mandatory missing but still need clarification, use generic questions
        # This should be rare with the new approach
        
        # If no specific variables identified, use generic questions based on context
        if not questions:
            if len(extracted_variables) > 0:
                # Have some variables but rules don't apply
                questions.extend([
                    "Are there any special circumstances or exceptions that might apply?",
                    "Does this situation involve any specific procedures or requirements?",
                    "What additional context would help evaluate this scenario?"
                ])
            else:
                # No variables extracted at all
                questions.extend([
                    "Could you provide more specific details about this scenario?",
                    "What are the key facts or conditions involved?",
                    "What specific outcome or decision are you trying to verify?"
                ])
        
        return questions[:3]  # Limit to 3 questions to avoid overwhelming
    
    def _generate_variable_question(self, var_name: str) -> str:
        """Generate a clarifying question for a specific variable based on its name"""
        var_lower = var_name.lower()
        
        # Employment-related variables
        if 'employee' in var_lower or 'worker' in var_lower:
            if 'type' in var_lower:
                return f"What type of {var_name.replace('_', ' ')} is this?"
            else:
                return f"Could you specify the {var_name.replace('_', ' ')}?"
        
        # Time-related variables
        if any(time_word in var_lower for time_word in ['days', 'hours', 'weeks', 'months', 'duration', 'time']):
            return f"What is the {var_name.replace('_', ' ')}?"
        
        # Approval/permission variables
        if any(approval_word in var_lower for approval_word in ['approval', 'permission', 'authorized', 'approved']):
            return f"Is there {var_name.replace('_', ' ')} for this request?"
        
        # Amount/quantity variables
        if any(amount_word in var_lower for amount_word in ['amount', 'cost', 'budget', 'quantity', 'number']):
            return f"What is the {var_name.replace('_', ' ')}?"
        
        # Status variables
        if 'status' in var_lower or 'state' in var_lower:
            return f"What is the current {var_name.replace('_', ' ')}?"
        
        # Generic question
        return f"Could you specify the {var_name.replace('_', ' ')}?"
    
    def compile_and_verify(self, policy_dict: Dict[str, Any], question: str, answer: str, extracted_variables: Dict[str, Any]) -> Dict[str, Any]:
        """Compile policy and verify in one step (for testing/development)"""
        
        try:
            # Compile the policy
            compiled_policy = self.rule_compiler.compile_policy(policy_dict)
            serialized_constraints = dumps_compilation(policy_dict, compiled_policy)
            
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