#!/usr/bin/env python3
"""
Complete end-to-end test of the mandatory variable system
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.variable_extractor import VariableExtractorService
from app.services.verification import VerificationService
import asyncio

async def test_complete_system():
    """Test complete system with generated policy"""
    
    print("🧪 Complete System Test: Generated Policy + Mandatory Variables")
    print("=" * 70)
    
    # Use the policy structure that was generated
    test_policy = {
        "policy_name": "Employee Vacation Policy",
        "domain": "hr", 
        "version": "1.0",
        "description": "Policy for employee vacation requests",
        "variables": [
            {
                "name": "employee_type",
                "type": "enum",
                "description": "Type of employment for the employee",
                "possible_values": ["full_time", "part_time"],
                "is_mandatory": True
            },
            {
                "name": "requested_days", 
                "type": "number",
                "description": "Number of consecutive vacation days requested",
                "is_mandatory": True
            },
            {
                "name": "advance_notice_days",
                "type": "number", 
                "description": "Number of days notice given before the vacation start date",
                "is_mandatory": True
            },
            {
                "name": "has_manager_approval",
                "type": "boolean",
                "description": "Indicates if the vacation request has manager approval", 
                "is_mandatory": False,
                "default_value": "false"
            },
            {
                "name": "leave_type",
                "type": "enum",
                "description": "Type of leave being requested",
                "possible_values": ["vacation", "emergency"],
                "is_mandatory": False  # No default - should skip rules
            }
        ],
        "rules": [
            {
                "id": "advance_notice_rule",
                "condition": "leave_type == 'vacation' AND advance_notice_days >= 14", 
                "conclusion": "valid",
                "description": "Vacation requests need 14+ days advance notice",
                "priority": 1
            },
            {
                "id": "manager_approval_rule",
                "condition": "requested_days > 5 AND has_manager_approval == true",
                "conclusion": "valid", 
                "description": "Long vacations need manager approval",
                "priority": 2
            },
            {
                "id": "emergency_rule",
                "condition": "leave_type == 'emergency'",
                "conclusion": "valid",
                "description": "Emergency leave bypasses normal rules", 
                "priority": 3
            }
        ],
        "constraints": []
    }
    
    # Test scenarios
    test_cases = [
        {
            "name": "Missing mandatory variables",
            "question": "Can I take some time off?",
            "answer": "I need some vacation time.",
            "expected_result": "needs_clarification"
        },
        {
            "name": "Valid request with defaults",
            "question": "Can full-time employee take 3 days vacation in 3 weeks?",
            "answer": "Yes, full-time employee wants 3 days vacation with 21 days notice.",
            "expected_result": "valid"  # Should use default has_manager_approval=false, skip leave_type rule
        },
        {
            "name": "Emergency leave (optional variable provided)",
            "question": "Can employee take emergency leave tomorrow?",
            "answer": "Employee needs emergency leave starting tomorrow for family situation.", 
            "expected_result": "valid"  # Emergency rule should apply
        }
    ]
    
    # Initialize services
    extractor = VariableExtractorService()
    verifier = VerificationService()
    
    print("🔧 Testing complete mandatory variable system...")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test Case {i}: {test_case['name']}")
        print("-" * 50)
        
        try:
            # Extract variables
            extracted = await extractor.extract_variables(
                test_case['question'],
                test_case['answer'],
                test_policy['variables']
            )
            
            print(f"📊 Extracted Variables:")
            for var, value in extracted.items():
                status = ""
                if value == "MISSING_MANDATORY":
                    status = " (❌ MISSING MANDATORY)"
                elif value == "SKIP_RULE":
                    status = " (⏭️ SKIP RULE)"
                elif value is None:
                    status = " (🟢 NULL)"
                print(f"  - {var}: {value}{status}")
            
            # Verify
            result = verifier.compile_and_verify(
                test_policy,
                test_case['question'], 
                test_case['answer'],
                extracted
            )
            
            print(f"🎯 Result: {result['result']}")
            print(f"📝 Explanation: {result['explanation']}")
            
            if result['result'] == test_case['expected_result']:
                print("✅ PASSED")
            else:
                print(f"❌ FAILED - Expected: {test_case['expected_result']}, Got: {result['result']}")
                
        except Exception as e:
            print(f"💥 ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n🎉 Complete System Test Finished!")

if __name__ == "__main__":
    asyncio.run(test_complete_system())