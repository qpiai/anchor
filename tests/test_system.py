#!/usr/bin/env python3
"""
Test script to verify the automated reasoning backend functionality
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.services.rule_compiler import RuleCompiler
from app.services.verification import VerificationService

def test_rule_compiler():
    """Test the rule compiler with a sample policy"""
    print("🧪 Testing Rule Compiler...")
    
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
    
    try:
        compiler = RuleCompiler()
        compiled_policy = compiler.compile_policy(policy_yaml)
        
        print("✅ Policy compiled successfully!")
        print(f"   Variables: {len(compiled_policy['variables'])}")
        print(f"   Rules: {len(compiled_policy['rules'])}")
        print(f"   Constraints: {len(compiled_policy['constraints'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Rule compilation failed: {e}")
        return False

def test_verification():
    """Test the verification service"""
    print("\n🧪 Testing Verification Service...")
    
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

constraints:
  - "advance_notice_days >= 0"
  - "vacation_duration_days > 0"
"""
    
    test_scenarios = [
        {
            'name': 'Valid regular vacation',
            'variables': {
                'advance_notice_days': 20,
                'vacation_duration_days': 3,
                'request_type': 'regular_vacation',
                'has_manager_approval': False
            },
            'expected': 'valid'
        },
        {
            'name': 'Invalid - insufficient notice',
            'variables': {
                'advance_notice_days': 5,
                'vacation_duration_days': 3,
                'request_type': 'regular_vacation',
                'has_manager_approval': False
            },
            'expected': 'invalid'
        },
        {
            'name': 'Invalid - long vacation without approval',
            'variables': {
                'advance_notice_days': 20,
                'vacation_duration_days': 10,
                'request_type': 'regular_vacation',
                'has_manager_approval': False
            },
            'expected': 'invalid'
        },
        {
            'name': 'Valid emergency leave',
            'variables': {
                'advance_notice_days': 0,
                'vacation_duration_days': 3,
                'request_type': 'emergency_leave',
                'has_manager_approval': False
            },
            'expected': 'valid'
        }
    ]
    
    try:
        verification_service = VerificationService()
        
        all_passed = True
        
        for scenario in test_scenarios:
            result = verification_service.compile_and_verify(
                policy_yaml, 
                "Test question",
                "Test answer", 
                scenario['variables']
            )
            
            if result['result'] == scenario['expected']:
                print(f"✅ {scenario['name']}: {result['result']} (expected {scenario['expected']})")
            else:
                print(f"❌ {scenario['name']}: {result['result']} (expected {scenario['expected']})")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Verification testing failed: {e}")
        return False

def test_z3_installation():
    """Test if Z3 is properly installed"""
    print("🧪 Testing Z3 Installation...")
    
    try:
        from z3 import Solver, IntVal, BoolVal
        
        # Simple Z3 test
        solver = Solver()
        x = IntVal(5)
        solver.add(x == 5)
        
        if solver.check().r == 1:  # SAT
            print("✅ Z3 solver is working correctly!")
            return True
        else:
            print("❌ Z3 solver returned unexpected result")
            return False
            
    except ImportError:
        print("❌ Z3 is not installed. Run: pip install z3-solver")
        return False
    except Exception as e:
        print(f"❌ Z3 test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Automated Reasoning Backend Tests\n")
    
    tests = [
        ("Z3 Installation", test_z3_installation),
        ("Rule Compiler", test_rule_compiler),
        ("Verification Service", test_verification),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print('='*50)
        
        success = test_func()
        results.append((test_name, success))
    
    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print('='*50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(results)} tests")
    
    if passed == len(results):
        print("\n🎉 All tests passed! The system is ready to use.")
        return 0
    else:
        print(f"\n⚠️  {len(results) - passed} test(s) failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 