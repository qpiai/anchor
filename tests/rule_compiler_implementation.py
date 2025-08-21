import yaml
import re
from z3 import *
from typing import Dict, List, Any, Union
from dataclasses import dataclass

@dataclass
class PolicyVariable:
    name: str
    type: str
    description: str
    possible_values: List[str] = None

@dataclass
class PolicyRule:
    id: str
    description: str
    condition: str
    conclusion: str
    priority: int = 1

class RuleCompiler:
    def __init__(self):
        self.variables = {}
        self.z3_vars = {}
        self.constraints = []
        
    def compile_policy(self, policy_yaml: str) -> Dict[str, Any]:
        """Main entry point - converts YAML policy to Z3 constraints"""
        policy = yaml.safe_load(policy_yaml)
        
        # Step 1: Create Z3 variables
        self._create_z3_variables(policy['variables'])
        
        # Step 2: Compile rules to Z3 constraints
        z3_rules = []
        for rule in policy['rules']:
            z3_constraint = self._compile_rule(rule)
            z3_rules.append({
                'id': rule['id'],
                'constraint': z3_constraint,
                'description': rule['description']
            })
        
        # Step 3: Compile global constraints
        z3_constraints = []
        if 'constraints' in policy:
            for constraint in policy['constraints']:
                z3_constraints.append(self._parse_condition(constraint))
        
        return {
            'variables': self.z3_vars,
            'rules': z3_rules,
            'constraints': z3_constraints,
            'variable_metadata': self.variables
        }
    
    def _create_z3_variables(self, variables: List[Dict]):
        """Create Z3 variables with proper types"""
        for var in variables:
            var_obj = PolicyVariable(**var)
            self.variables[var['name']] = var_obj
            
            # Create Z3 variable based on type
            if var['type'] == 'string':
                self.z3_vars[var['name']] = String(var['name'])
            elif var['type'] == 'number':
                self.z3_vars[var['name']] = Int(var['name'])
            elif var['type'] == 'boolean':
                self.z3_vars[var['name']] = Bool(var['name'])
            elif var['type'] == 'date':
                # Represent dates as integers (days since epoch)
                self.z3_vars[var['name']] = Int(var['name'])
            elif var['type'] == 'enum':
                # Create constraints for enum values
                self.z3_vars[var['name']] = String(var['name'])
                # Add constraint that variable must be one of possible values
                enum_constraint = Or([self.z3_vars[var['name']] == val 
                                    for val in var['possible_values']])
                self.constraints.append(enum_constraint)
    
    def _compile_rule(self, rule: Dict) -> Any:
        """Compile a single rule to Z3 constraint"""
        condition = self._parse_condition(rule['condition'])
        
        if rule['conclusion'] == 'valid':
            # Rule passes when condition is true
            return condition
        elif rule['conclusion'] == 'invalid':
            # Rule fails when condition is true (so we negate it)
            return Not(condition)
        else:
            # Custom conclusion - more complex logic
            conclusion = self._parse_condition(rule['conclusion'])
            return Implies(condition, conclusion)
    
    def _parse_condition(self, condition: str) -> Any:
        """Parse logical condition string into Z3 expression"""
        # Clean up the condition string
        condition = condition.strip()
        
        # Handle logical operators (order matters!)
        if ' OR ' in condition:
            return self._parse_or_condition(condition)
        elif ' AND ' in condition:
            return self._parse_and_condition(condition)
        elif condition.startswith('NOT '):
            inner = condition[4:].strip()
            return Not(self._parse_condition(inner))
        else:
            return self._parse_atomic_condition(condition)
    
    def _parse_or_condition(self, condition: str) -> Any:
        """Parse OR conditions"""
        parts = [part.strip() for part in condition.split(' OR ')]
        z3_parts = [self._parse_condition(part) for part in parts]
        return Or(z3_parts)
    
    def _parse_and_condition(self, condition: str) -> Any:
        """Parse AND conditions"""
        parts = [part.strip() for part in condition.split(' AND ')]
        z3_parts = [self._parse_condition(part) for part in parts]
        return And(z3_parts)
    
    def _parse_atomic_condition(self, condition: str) -> Any:
        """Parse atomic conditions like 'x == 5' or 'name != "john"'"""
        
        # Handle parentheses
        if condition.startswith('(') and condition.endswith(')'):
            return self._parse_condition(condition[1:-1])
        
        # Comparison operators (order matters - check >= before >)
        operators = ['>=', '<=', '!=', '==', '>', '<']
        
        for op in operators:
            if op in condition:
                left, right = condition.split(op, 1)
                left = left.strip()
                right = right.strip()
                
                # Get Z3 variables
                left_var = self._get_z3_expression(left)
                right_var = self._get_z3_expression(right)
                
                # Return appropriate Z3 constraint
                if op == '==':
                    return left_var == right_var
                elif op == '!=':
                    return left_var != right_var
                elif op == '>':
                    return left_var > right_var
                elif op == '<':
                    return left_var < right_var
                elif op == '>=':
                    return left_var >= right_var
                elif op == '<=':
                    return left_var <= right_var
        
        raise ValueError(f"Could not parse atomic condition: {condition}")
    
    def _get_z3_expression(self, expr: str) -> Any:
        """Convert expression to Z3 variable or constant"""
        expr = expr.strip()
        
        # Remove quotes for strings
        if expr.startswith('"') and expr.endswith('"'):
            return StringVal(expr[1:-1])
        elif expr.startswith("'") and expr.endswith("'"):
            return StringVal(expr[1:-1])
        
        # Try to parse as number
        try:
            if '.' in expr:
                return RealVal(float(expr))
            else:
                return IntVal(int(expr))
        except ValueError:
            pass
        
        # Check if it's a boolean
        if expr.lower() in ['true', 'false']:
            return BoolVal(expr.lower() == 'true')
        
        # Must be a variable name
        if expr in self.z3_vars:
            return self.z3_vars[expr]
        else:
            raise ValueError(f"Unknown variable: {expr}")

# Example usage and testing
def test_rule_compiler():
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
    description: "Regular vacation needs 2+ weeks notice"
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

    # Compile the policy
    compiler = RuleCompiler()
    compiled_policy = compiler.compile_policy(policy_yaml)
    
    print("=== Compiled Policy ===")
    print(f"Variables: {list(compiled_policy['variables'].keys())}")
    print(f"Rules: {len(compiled_policy['rules'])}")
    print(f"Constraints: {len(compiled_policy['constraints'])}")
    
    # Test with Z3 solver
    solver = Solver()
    
    # Add all constraints
    for constraint in compiled_policy['constraints']:
        solver.add(constraint)
    
    # Test a specific scenario
    vars = compiled_policy['variables']
    
    # Scenario: Regular vacation, 10 days notice, 3 days duration, no approval
    solver.push()  # Save state
    solver.add(vars['request_type'] == StringVal('regular_vacation'))
    solver.add(vars['advance_notice_days'] == IntVal(10))
    solver.add(vars['vacation_duration_days'] == IntVal(3)) 
    solver.add(vars['has_manager_approval'] == BoolVal(False))
    
    # Check each rule
    for rule in compiled_policy['rules']:
        solver.push()
        solver.add(Not(rule['constraint']))  # Try to violate the rule
        if solver.check() == unsat:
            print(f"✅ Rule {rule['id']}: PASSES")
        else:
            print(f"❌ Rule {rule['id']}: FAILS - {rule['description']}")
        solver.pop()
    
    solver.pop()  # Restore state

if __name__ == "__main__":
    test_rule_compiler()