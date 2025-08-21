#!/usr/bin/env python3
"""
Comprehensive test suite for the new mandatory variable system.
Tests all edge cases:
1. Mandatory variables missing -> needs_clarification 
2. Optional variables with defaults -> use defaults
3. Optional variables without defaults -> skip rules
4. Mixed scenarios with all combinations
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.variable_extractor import VariableExtractorService
from app.services.verification import VerificationService
import asyncio
import json

async def test_mandatory_variable_system():
    """Test the comprehensive mandatory variable system"""
    
    print("🧪 Testing Mandatory Variable System")
    print("=" * 50)
    
    # Create test policy with mixed mandatory/optional variables
    test_policy = {
        "name": "test_mandatory_system",
        "domain": "test",
        "version": "1.0",
        "description": "Test policy for mandatory variable system",
        "variables": [
            {
                "name": "employee_id",
                "type": "string", 
                "description": "Employee identifier",
                "is_mandatory": True  # No default - must be provided
            },
            {
                "name": "request_amount",
                "type": "number",
                "description": "Amount requested",
                "is_mandatory": True  # No default - must be provided
            },
            {
                "name": "department",
                "type": "string",
                "description": "Employee department", 
                "is_mandatory": False,
                "default_value": "general"  # Optional with default
            },
            {
                "name": "urgency_level",
                "type": "enum",
                "description": "How urgent is this request",
                "possible_values": ["low", "medium", "high"],
                "is_mandatory": False,
                "default_value": "medium"  # Optional with default
            },
            {
                "name": "has_backup_coverage",
                "type": "boolean", 
                "description": "Whether someone can cover duties",
                "is_mandatory": False  # Optional without default - should skip rules
            }
        ],
        "rules": [
            {
                "id": "mandatory_info_rule",
                "condition": "employee_id != '' AND request_amount > 0",
                "conclusion": "valid",
                "description": "Basic mandatory information provided",
                "priority": 1
            },
            {
                "id": "department_rule", 
                "condition": "department == 'finance' AND request_amount > 1000",
                "conclusion": "invalid",
                "description": "Finance dept cannot request over 1000",
                "priority": 2
            },
            {
                "id": "urgency_rule",
                "condition": "urgency_level == 'high' AND request_amount > 500", 
                "conclusion": "invalid",
                "description": "High urgency requests cannot exceed 500",
                "priority": 3
            },
            {
                "id": "backup_rule",
                "condition": "has_backup_coverage == false AND request_amount > 100",
                "conclusion": "invalid", 
                "description": "Large requests need backup coverage",
                "priority": 4
            }
        ],
        "constraints": [
            "request_amount >= 0"
        ]
    }
    
    # Initialize services
    extractor = VariableExtractorService()
    verifier = VerificationService()
    
    # Test scenarios covering all edge cases
    test_cases = [
        {
            "name": "Case 1: Missing mandatory variables",
            "question": "Can I request something?",
            "answer": "I need to submit a request.", 
            "expected_result": "needs_clarification",
            "expected_missing": ["employee_id", "request_amount"]
        },
        {
            "name": "Case 2: Mandatory provided, optional uses defaults", 
            "question": "Can employee EMP123 request $50?",
            "answer": "Yes, EMP123 wants to request $50.",
            "expected_result": "valid",
            "expected_defaults_used": ["department", "urgency_level"]
        },
        {
            "name": "Case 3: Optional without default causes rule skipping",
            "question": "Can employee EMP456 request $150?", 
            "answer": "EMP456 needs $150 for equipment.",
            "expected_result": "valid",  # backup_rule should be skipped
            "expected_skipped": ["has_backup_coverage"]
        },
        {
            "name": "Case 4: Optional with default causes rule violation",
            "question": "Can employee EMP789 from finance request $1200?",
            "answer": "EMP789 works in finance and needs $1200.",
            "expected_result": "invalid",  # department_rule should trigger
            "expected_rule_violated": "department_rule"
        },
        {
            "name": "Case 5: Mix of all scenarios",
            "question": "Can employee EMP999 request $600 urgently?", 
            "answer": "EMP999 needs $600 with high urgency for a project.",
            "expected_result": "invalid",  # urgency_rule should trigger
            "expected_rule_violated": "urgency_rule"
        }
    ]
    
    # Run test cases
    for i, test_case in enumerate(test_cases):
        print(f"\n🔬 {test_case['name']}")
        print("-" * 40)
        
        try:
            # Extract variables using new system
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
            
            # Verify scenario
            result = verifier.compile_and_verify(
                test_policy,
                test_case['question'],
                test_case['answer'],
                extracted
            )
            
            print(f"🎯 Result: {result['result']}")
            print(f"📝 Explanation: {result['explanation']}")
            
            # Validate expectations
            success = True
            if result['result'] != test_case['expected_result']:
                print(f"❌ FAILED: Expected {test_case['expected_result']}, got {result['result']}")
                success = False
            
            # Check for expected missing mandatory variables
            if 'expected_missing' in test_case:
                missing = [var for var, val in extracted.items() if val == "MISSING_MANDATORY"]
                if not all(var in missing for var in test_case['expected_missing']):
                    print(f"❌ FAILED: Expected missing {test_case['expected_missing']}, got {missing}")
                    success = False
            
            # Check for expected skipped variables
            if 'expected_skipped' in test_case:
                skipped = [var for var, val in extracted.items() if val == "SKIP_RULE"]
                if not all(var in skipped for var in test_case['expected_skipped']):
                    print(f"❌ FAILED: Expected skipped {test_case['expected_skipped']}, got {skipped}")
                    success = False
            
            if success:
                print(f"✅ PASSED")
            
        except Exception as e:
            print(f"💥 ERROR: {str(e)}")
            import traceback
            traceback.print_exc()

async def main():
    """Main test function"""
    await test_mandatory_variable_system()
    print("\n🎉 Mandatory Variable System Test Complete!")

if __name__ == "__main__":
    asyncio.run(main())