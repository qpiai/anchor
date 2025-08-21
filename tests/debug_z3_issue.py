#!/usr/bin/env python3
"""
Debug the Z3 sort mismatch issue
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.variable_extractor import VariableExtractorService
from app.services.verification import VerificationService
import asyncio
import json

async def debug_z3_issue():
    """Debug the Z3 sort mismatch issue"""
    
    # Simple test policy
    test_policy = {
        "name": "debug_policy",
        "domain": "test",
        "version": "1.0",
        "description": "Debug policy for Z3 issue",
        "variables": [
            {
                "name": "employee_id",
                "type": "string", 
                "description": "Employee identifier",
                "is_mandatory": True
            },
            {
                "name": "request_amount",
                "type": "number",
                "description": "Amount requested",
                "is_mandatory": True
            },
            {
                "name": "department",
                "type": "string",
                "description": "Employee department", 
                "is_mandatory": False,
                "default_value": "general"
            },
            {
                "name": "urgency_level",
                "type": "enum",
                "description": "How urgent is this request",
                "possible_values": ["low", "medium", "high"],
                "is_mandatory": False,
                "default_value": "medium"
            },
            {
                "name": "has_backup_coverage",
                "type": "boolean", 
                "description": "Whether someone can cover duties",
                "is_mandatory": False
            }
        ],
        "rules": [
            {
                "id": "basic_rule",
                "condition": "employee_id != '' AND request_amount > 0",
                "conclusion": "valid",
                "description": "Basic validation",
                "priority": 1
            },
            {
                "id": "backup_rule",
                "condition": "has_backup_coverage == false AND request_amount > 100",
                "conclusion": "invalid", 
                "description": "Large requests need backup coverage",
                "priority": 2
            }
        ],
        "constraints": []
    }
    
    # Initialize services
    extractor = VariableExtractorService()
    verifier = VerificationService()
    
    # Extract variables
    print("🔍 Extracting variables...")
    extracted = await extractor.extract_variables(
        "Can employee EMP123 request $50?",
        "Yes, EMP123 wants to request $50.",
        test_policy['variables']
    )
    
    print(f"📊 Extracted Variables:")
    for var, value in extracted.items():
        print(f"  - {var}: {value} (type: {type(value)})")
    
    # Try compilation first
    print("\n🔧 Compiling policy...")
    try:
        from app.services.rule_compiler import RuleCompiler
        compiler = RuleCompiler()
        compiled = compiler.compile_policy(test_policy)
        print("✅ Policy compiled successfully")
        
        # Check Z3 variables
        print(f"📈 Z3 Variables created:")
        for name, z3_var in compiled['variables'].items():
            print(f"  - {name}: {z3_var} (Z3 type: {z3_var.sort()})")
            
    except Exception as e:
        print(f"❌ Compilation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Test rule dependency detection
    print("\n🔍 Testing rule dependency detection...")
    skipped_variables = ["has_backup_coverage"]
    
    for rule in compiled['rules']:
        depends = verifier._rule_depends_on_variables(rule, skipped_variables)
        print(f"Rule '{rule['id']}' depends on skipped vars: {depends}")
        if rule.get('original_rule'):
            print(f"  Original condition: {rule['original_rule'].get('condition', 'N/A')}")
    
    # Try verification
    print("\n✅ Verifying scenario...")
    try:
        result = verifier.compile_and_verify(
            test_policy,
            "Can employee EMP123 request $50?",
            "Yes, EMP123 wants to request $50.",
            extracted
        )
        
        print(f"🎯 Result: {result['result']}")
        print(f"📝 Explanation: {result['explanation']}")
        
    except Exception as e:
        print(f"❌ Verification failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_z3_issue())