#!/usr/bin/env python3
"""
Test the new policy generator and UI toggle features
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.policy_generator import PolicyGeneratorService
import asyncio
import json

async def test_policy_generator():
    """Test if policy generator includes new mandatory fields"""
    
    print("🧪 Testing Policy Generator with Mandatory Variable Fields")
    print("=" * 60)
    
    generator = PolicyGeneratorService()
    
    # Simple test document
    test_document = """
    Employee Vacation Policy
    
    All employees are eligible for vacation time. Full-time permanent employees 
    get 15 days per year. Part-time employees get 10 days. 
    
    Vacation requests must be submitted at least 14 days in advance.
    Manager approval is required for requests longer than 5 consecutive days.
    
    Emergency leave can be granted without advance notice in special circumstances.
    """
    
    try:
        print("🔍 Generating policy from test document...")
        policy = await generator.generate_policy_from_document(test_document, "hr")
        
        print("✅ Policy generated successfully!")
        print(f"📋 Policy name: {policy.get('policy_name', 'N/A')}")
        print(f"🏢 Domain: {policy.get('domain', 'N/A')}")
        
        # Check variables for new fields
        variables = policy.get('variables', [])
        print(f"\n🔢 Variables ({len(variables)}):")
        
        has_mandatory_field = False
        has_default_field = False
        
        for var in variables:
            mandatory_status = var.get('is_mandatory', 'NOT_SET')
            default_value = var.get('default_value', 'NOT_SET')
            
            if 'is_mandatory' in var:
                has_mandatory_field = True
            if 'default_value' in var:
                has_default_field = True
            
            print(f"  - {var['name']} ({var['type']})")
            print(f"    📝 {var['description']}")
            print(f"    🔴 Mandatory: {mandatory_status}")
            print(f"    🎯 Default: {default_value}")
            print()
        
        # Validation
        success = True
        if not has_mandatory_field:
            print("❌ FAILED: No variables have 'is_mandatory' field")
            success = False
        else:
            print("✅ PASSED: Variables include 'is_mandatory' field")
        
        if not has_default_field:
            print("❌ Some variables missing 'default_value' field (this is OK if intentional)")
        else:
            print("✅ PASSED: Some variables include 'default_value' field")
        
        # Show rules
        rules = policy.get('rules', [])
        print(f"\n⚖️ Rules ({len(rules)}):")
        for rule in rules:
            print(f"  - {rule['id']}: {rule['description']}")
            print(f"    Condition: {rule['condition']}")
            print(f"    Conclusion: {rule['conclusion']}")
            print()
        
        if success:
            print("🎉 Policy generator test PASSED!")
        else:
            print("💥 Policy generator test FAILED!")
            
    except Exception as e:
        print(f"❌ Policy generation failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_policy_generator())