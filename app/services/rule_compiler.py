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
    is_mandatory: bool = True
    default_value: str = None
    trusted_only: bool = False

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
        
    def compile_policy(self, policy_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point - converts policy dictionary to Z3 constraints"""
        self.variables = {}
        self.z3_vars = {}
        self.constraints = []
        policy = policy_dict
        
        # Step 1: Create Z3 variables
        self._create_z3_variables(policy['variables'])
        
        # Step 2: Compile rules to Z3 constraints
        z3_rules = []
        for rule in policy['rules']:
            compiled_rule = self._compile_rule(rule)
            z3_rules.append({
                'id': rule['id'],
                'constraint': compiled_rule['constraint'],
                'conclusion': compiled_rule['conclusion'],
                'description': rule['description'],
                'original_rule': rule
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
            'variable_metadata': self.variables,
            'serializable_data': self._create_serializable_data(z3_rules, z3_constraints)
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
                # Reals so fractional inputs (0.5 hours) compare correctly.
                # Integer inputs still bind with RealVal.
                self.z3_vars[var['name']] = Real(var['name'])
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
    
    def _create_serializable_data(self, z3_rules: List[Dict], z3_constraints: List[Any]) -> Dict[str, Any]:
        """Create serializable representation of Z3 data"""
        serializable_rules = []
        for rule in z3_rules:
            serializable_rules.append({
                'id': rule['id'],
                'description': rule['description'],
                'constraint_str': str(rule['constraint'])  # Convert Z3 to string
            })
        
        serializable_constraints = [str(constraint) for constraint in z3_constraints]
        
        # Also include variable information for reconstruction
        variable_info = {}
        for name, var_obj in self.variables.items():
            variable_info[name] = {
                'name': var_obj.name,
                'type': var_obj.type,
                'description': var_obj.description,
                'possible_values': var_obj.possible_values
            }
        
        return {
            'rules': serializable_rules,
            'constraints': serializable_constraints,
            'variables': variable_info
        }

    def _compile_rule(self, rule: Dict) -> Dict[str, Any]:
        """Compile a single rule to Z3 constraint with metadata
        
        Rules should be interpreted as logical implications:
        - 'valid' conclusion: IF condition THEN scenario is valid  
        - 'invalid' conclusion: IF condition THEN scenario is invalid
        
        Returns dict with constraint, condition, conclusion for better evaluation
        """
        condition = self._parse_condition(rule['condition'])
        
        return {
            'constraint': condition,
            'conclusion': rule['conclusion'],
            'original_rule': rule
        }
    
    def _parse_condition(self, condition: str) -> Any:
        """Parse logical condition string into Z3 expression"""
        # Clean up the condition string
        condition = condition.strip()
        
        # Handle parentheses at the top level first
        if condition.startswith('(') and condition.endswith(')'):
            # Remove outer parentheses and parse the inner content
            return self._parse_condition(condition[1:-1])
        
        # Handle logical operators (order matters!)
        if ' OR ' in condition and not self._is_in_parentheses(condition, ' OR '):
            return self._parse_or_condition(condition)
        elif ' AND ' in condition and not self._is_in_parentheses(condition, ' AND '):
            return self._parse_and_condition(condition)
        elif condition.startswith('NOT '):
            inner = condition[4:].strip()
            return Not(self._parse_condition(inner))
        else:
            return self._parse_atomic_condition(condition)
    
    def _is_in_parentheses(self, text: str, operator: str) -> bool:
        """Check if ALL instances of operator are within parentheses"""
        paren_depth = 0
        i = 0
        while i < len(text):
            if text[i] == '(':
                paren_depth += 1
            elif text[i] == ')':
                paren_depth -= 1
            elif paren_depth == 0 and text[i:i+len(operator)] == operator:
                return False  # Found operator at top level
            i += 1
        return True  # All operators are within parentheses
    
    def _parse_or_condition(self, condition: str) -> Any:
        """Parse OR conditions respecting parentheses"""
        parts = self._split_respecting_parentheses(condition, ' OR ')
        z3_parts = [self._parse_condition(part.strip()) for part in parts]
        return Or(z3_parts)
    
    def _parse_and_condition(self, condition: str) -> Any:
        """Parse AND conditions respecting parentheses"""
        parts = self._split_respecting_parentheses(condition, ' AND ')
        z3_parts = [self._parse_condition(part.strip()) for part in parts]
        return And(z3_parts)
    
    def _split_respecting_parentheses(self, text: str, delimiter: str) -> List[str]:
        """Split text on delimiter while respecting parentheses"""
        parts = []
        current_part = ""
        paren_depth = 0
        i = 0
        
        while i < len(text):
            if text[i] == '(':
                paren_depth += 1
                current_part += text[i]
            elif text[i] == ')':
                paren_depth -= 1
                current_part += text[i]
            elif paren_depth == 0 and text[i:i+len(delimiter)] == delimiter:
                # Found delimiter at top level
                parts.append(current_part)
                current_part = ""
                i += len(delimiter) - 1  # Skip the delimiter
            else:
                current_part += text[i]
            i += 1
        
        # Add the last part
        if current_part:
            parts.append(current_part)
        
        return parts
    
    def _parse_atomic_condition(self, condition: str) -> Any:
        """Parse atomic conditions like 'x == 5', 'name != "john"', or boolean variables"""
        
        # Handle parentheses
        if condition.startswith('(') and condition.endswith(')'):
            return self._parse_condition(condition[1:-1])
        
        # Handle NOT operator for boolean variables
        if condition.strip().upper().startswith('NOT '):
            inner_condition = condition.strip()[4:].strip()
            # If it's just a variable name, treat as boolean
            if inner_condition in self.z3_vars and self.variables[inner_condition].type == 'boolean':
                return Not(self.z3_vars[inner_condition])
            else:
                # Parse the inner condition and negate it
                return Not(self._parse_atomic_condition(inner_condition))
        
        # Handle IN operator for array membership (e.g., "x IN ['a', 'b', 'c']")
        if ' IN ' in condition:
            left, right = condition.split(' IN ', 1)
            left = left.strip()
            right = right.strip()
            
            # Parse the array on the right side
            if right.startswith('[') and right.endswith(']'):
                # Extract array elements
                array_content = right[1:-1].strip()
                if array_content:
                    # Split by comma and clean up quotes
                    elements = []
                    for elem in array_content.split(','):
                        elem = elem.strip()
                        if elem.startswith('"') and elem.endswith('"'):
                            elements.append(elem[1:-1])
                        elif elem.startswith("'") and elem.endswith("'"):
                            elements.append(elem[1:-1])
                        else:
                            elements.append(elem)
                    
                    # Create Z3 constraint for membership
                    left_var = self._get_z3_expression(left)
                    or_conditions = []
                    for element in elements:
                        or_conditions.append(left_var == StringVal(element))
                    
                    return Or(or_conditions) if len(or_conditions) > 1 else or_conditions[0]
            
            raise ValueError(f"Invalid IN syntax: {condition}")
        
        # Comparison operators (order matters - check >= before >)
        operators = ['>=', '<=', '!=', '==', '>', '<']
        
        for op in operators:
            if op in condition:
                left, right = condition.split(op, 1)
                left = left.strip()
                right = right.strip()
                
                # Get Z3 variables. Integer literals become Reals when
                # compared with a number variable so the sorts match.
                left_var = self._get_z3_expression(left)
                right_var = self._get_z3_expression(right)
                left_var, right_var = self._align_numeric_sorts(left_var, right_var)
                
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
        
        # Handle standalone boolean variables (e.g., "is_active" means "is_active == true")
        condition_clean = condition.strip()
        if condition_clean in self.z3_vars and self.variables[condition_clean].type == 'boolean':
            return self.z3_vars[condition_clean]
        
        raise ValueError(f"Could not parse atomic condition: {condition}")

    def _align_numeric_sorts(self, left: Any, right: Any) -> tuple:
        """Promote an integer literal when the other side is a Real."""
        if is_real(left) and is_int_value(right):
            return left, RealVal(right.as_long())
        if is_real(right) and is_int_value(left):
            return RealVal(left.as_long()), right
        return left, right
    
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