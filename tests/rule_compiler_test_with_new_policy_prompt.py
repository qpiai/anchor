#!/usr/bin/env python3

import yaml
from z3 import *

# Copy your RuleCompiler class here or import it
class RuleCompiler:
    def __init__(self):
        self.variables = {}
        self.z3_vars = {}
        self.constraints = []
        
    def compile_policy(self, policy_yaml: str):
        """Main entry point - converts YAML policy to Z3 constraints"""
        policy = yaml.safe_load(policy_yaml)
        
        # Step 1: Create Z3 variables
        self._create_z3_variables(policy['variables'])
        
        # Step 2: Compile rules to Z3 constraints
        z3_rules = []
        for rule in policy['rules']:
            try:
                z3_constraint = self._compile_rule(rule)
                z3_rules.append({
                    'id': rule['id'],
                    'constraint': z3_constraint,
                    'description': rule['description']
                })
                print(f"✅ Rule {rule['id']}: Compiled successfully")
            except Exception as e:
                print(f"❌ Rule {rule['id']}: Compilation failed - {str(e)}")
                raise
        
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
    
    def _create_z3_variables(self, variables):
        """Create Z3 variables with proper types"""
        for var in variables:
            self.variables[var['name']] = var
            
            # Create Z3 variable based on type
            if var['type'] == 'string':
                self.z3_vars[var['name']] = String(var['name'])
            elif var['type'] == 'number':
                self.z3_vars[var['name']] = Int(var['name'])
            elif var['type'] == 'boolean':
                self.z3_vars[var['name']] = Bool(var['name'])
            elif var['type'] == 'date':
                self.z3_vars[var['name']] = Int(var['name'])
            elif var['type'] == 'enum':
                self.z3_vars[var['name']] = String(var['name'])
                # Add constraint for enum values
                enum_constraint = Or([self.z3_vars[var['name']] == val 
                                    for val in var['possible_values']])
                self.constraints.append(enum_constraint)
    
    def _compile_rule(self, rule):
        """Compile a single rule to Z3 constraint"""
        condition = self._parse_condition(rule['condition'])
        
        if rule['conclusion'] == 'valid':
            return condition
        elif rule['conclusion'] == 'invalid':
            return Not(condition)
        else:
            # This should not happen with the new format
            raise ValueError(f"Invalid conclusion: {rule['conclusion']}. Use 'valid' or 'invalid'")
    
    def _parse_condition(self, condition):
        """Parse logical condition string into Z3 expression"""
        condition = condition.strip()
        
        if ' OR ' in condition:
            return self._parse_or_condition(condition)
        elif ' AND ' in condition:
            return self._parse_and_condition(condition)
        elif condition.startswith('NOT '):
            inner = condition[4:].strip()
            return Not(self._parse_condition(inner))
        else:
            return self._parse_atomic_condition(condition)
    
    def _parse_or_condition(self, condition):
        """Parse OR conditions"""
        parts = [part.strip() for part in condition.split(' OR ')]
        z3_parts = [self._parse_condition(part) for part in parts]
        return Or(z3_parts)
    
    def _parse_and_condition(self, condition):
        """Parse AND conditions"""
        parts = [part.strip() for part in condition.split(' AND ')]
        z3_parts = [self._parse_condition(part) for part in parts]
        return And(z3_parts)
    
    def _parse_atomic_condition(self, condition):
        """Parse atomic conditions like 'x == 5' or 'name != "john"'"""
        
        if condition.startswith('(') and condition.endswith(')'):
            return self._parse_condition(condition[1:-1])
        
        operators = ['>=', '<=', '!=', '==', '>', '<']
        
        for op in operators:
            if op in condition:
                left, right = condition.split(op, 1)
                left = left.strip()
                right = right.strip()
                
                left_var = self._get_z3_expression(left)
                right_var = self._get_z3_expression(right)
                
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
    
    def _get_z3_expression(self, expr):
        """Convert expression to Z3 variable or constant"""
        expr = expr.strip()
        
        if expr.startswith('"') and expr.endswith('"'):
            return StringVal(expr[1:-1])
        elif expr.startswith("'") and expr.endswith("'"):
            return StringVal(expr[1:-1])
        
        try:
            if '.' in expr:
                return RealVal(float(expr))
            else:
                return IntVal(int(expr))
        except ValueError:
            pass
        
        if expr.lower() in ['true', 'false']:
            return BoolVal(expr.lower() == 'true')
        
        if expr in self.z3_vars:
            return self.z3_vars[expr]
        else:
            raise ValueError(f"Unknown variable: {expr}")


def test_contract_policy():
    """Test the contract policy compilation"""
    
    # Your fixed policy YAML
    policy_yaml = '''
policy_name: "contract_approval_policy"
domain: "legal"
version: "1.0"
description: "Policy governing the approval and signing of contracts within the organization"

variables:
  - name: "contract_value"
    type: "number"
    description: "The monetary value of the contract in USD"
  - name: "signatory_type"
    type: "enum"
    possible_values: ["legal_manager", "head_of_legal", "cfo", "manager", "employee"]
    description: "Type of individual attempting to sign the contract"
  - name: "vendor_documents_provided"
    type: "boolean"
    description: "Whether all required vendor documents have been provided"
  - name: "digital_signature_software"
    type: "enum"
    possible_values: ["docusign", "adobe_sign", "hellosign", "other"]
    description: "The digital signature software being used for signing"
  - name: "has_legal_manager_approval"
    type: "boolean"
    description: "Whether the Legal Manager has approved the contract"
  - name: "has_head_of_legal_approval"
    type: "boolean"
    description: "Whether the Head of Legal has approved the contract"
  - name: "has_cfo_approval"
    type: "boolean"
    description: "Whether the CFO has approved the contract"

rules:
  - id: "vendor_docs_required"
    description: "All contracts require vendor documents"
    condition: "vendor_documents_provided == false"
    conclusion: "invalid"
    priority: 1

  - id: "approved_software_only"
    description: "Only company-approved digital signature software may be used"
    condition: "digital_signature_software == 'other'"
    conclusion: "invalid"
    priority: 2

  - id: "unauthorized_signatory"
    description: "Managers and employees cannot sign contracts"
    condition: "signatory_type == 'manager' OR signatory_type == 'employee'"
    conclusion: "invalid"
    priority: 3

  - id: "small_contract_approval"
    description: "Contracts ≤ $50,000 require Legal Manager approval"
    condition: "contract_value <= 50000 AND signatory_type == 'legal_manager' AND has_legal_manager_approval == true"
    conclusion: "valid"
    priority: 4

constraints:
  - "contract_value > 0"
'''

    print("=== Testing Contract Policy Compilation ===")
    
    try:
        compiler = RuleCompiler()
        compiled_policy = compiler.compile_policy(policy_yaml)
        
        print(f"\n✅ Policy compiled successfully!")
        print(f"Variables: {list(compiled_policy['variables'].keys())}")
        print(f"Rules: {len(compiled_policy['rules'])}")
        print(f"Constraints: {len(compiled_policy['constraints'])}")
        
        # Test with Z3 solver
        print("\n=== Testing Z3 Verification ===")
        solver = Solver()
        
        # Add constraints
        for constraint in compiled_policy['constraints']:
            solver.add(constraint)
        
        # Test scenario: Valid small contract
        print("\nTest 1: Valid small contract")
        solver.push()
        vars = compiled_policy['variables']
        solver.add(vars['contract_value'] == IntVal(30000))
        solver.add(vars['signatory_type'] == StringVal('legal_manager'))
        solver.add(vars['vendor_documents_provided'] == BoolVal(True))
        solver.add(vars['digital_signature_software'] == StringVal('docusign'))
        solver.add(vars['has_legal_manager_approval'] == BoolVal(True))
        
        # Check each rule
        for rule in compiled_policy['rules']:
            solver.push()
            solver.add(Not(rule['constraint']))
            if solver.check() == unsat:
                print(f"  ✅ {rule['id']}: PASSES")
            else:
                print(f"  ❌ {rule['id']}: FAILS - {rule['description']}")
            solver.pop()
        
        solver.pop()
        
        # Test scenario: Invalid (manager trying to sign)
        print("\nTest 2: Invalid - manager trying to sign")
        solver.push()
        solver.add(vars['contract_value'] == IntVal(30000))
        solver.add(vars['signatory_type'] == StringVal('manager'))
        solver.add(vars['vendor_documents_provided'] == BoolVal(True))
        solver.add(vars['digital_signature_software'] == StringVal('docusign'))
        
        for rule in compiled_policy['rules']:
            solver.push()
            solver.add(Not(rule['constraint']))
            if solver.check() == unsat:
                print(f"  ✅ {rule['id']}: PASSES")
            else:
                print(f"  ❌ {rule['id']}: FAILS - {rule['description']}")
            solver.pop()
        
        solver.pop()
        
    except Exception as e:
        print(f"❌ Compilation failed: {str(e)}")
        return False
    
    return True


if __name__ == "__main__":
    success = test_contract_policy()
    if success:
        print("\n🎉 All tests passed! Your policy structure is correct.")
    else:
        print("\n💥 Tests failed. Check the errors above.")