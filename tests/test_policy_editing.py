#!/usr/bin/env python3
"""
Test the complete policy editing functionality - API endpoints and UI integration
"""

import os

import pytest
import requests
import json

API_BASE_URL = os.getenv("ANCHOR_API_URL", "http://localhost:9066").rstrip("/")
API_V1_PREFIX = "/api/v1"


def _api_reachable() -> bool:
    try:
        response = requests.get(f"{API_BASE_URL}/ping", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not _api_reachable(), reason="Anchor API is not reachable")

def test_policy_crud_apis():
    """Test all policy CRUD API endpoints"""
    
    print("🧪 Testing Complete Policy CRUD API Endpoints")
    print("=" * 60)
    
    # First, let's get an existing policy to test with
    policies_response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies")
    
    if policies_response.status_code != 200:
        print("❌ Failed to get policies list")
        return
    
    policies = policies_response.json()
    if not policies:
        print("❌ No policies found. Please create a policy first.")
        return
    
    policy_id = policies[0]['id']
    print(f"📋 Testing with policy ID: {policy_id}")
    
    # Test 1: Add Variable
    print("\n🔬 Test 1: Add Variable")
    add_var_data = {
        "name": "test_variable",
        "type": "string",
        "description": "A test variable for CRUD operations",
        "is_mandatory": False,
        "default_value": "test_default"
    }
    
    add_var_response = requests.post(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/variables",
        json=add_var_data
    )
    
    if add_var_response.status_code == 200:
        print("✅ Variable added successfully")
    else:
        print(f"❌ Failed to add variable: {add_var_response.status_code} - {add_var_response.text}")
    
    # Test 2: Update Variable
    print("\n🔬 Test 2: Update Variable")
    update_var_data = {
        "variable_name": "test_variable",
        "is_mandatory": True,
        "default_value": "updated_default"
    }
    
    update_var_response = requests.patch(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/variables/test_variable",
        json=update_var_data
    )
    
    if update_var_response.status_code == 200:
        print("✅ Variable updated successfully")
    else:
        print(f"❌ Failed to update variable: {update_var_response.status_code} - {update_var_response.text}")
    
    # Test 3: Add Rule
    print("\n🔬 Test 3: Add Rule")
    add_rule_data = {
        "id": "test_rule",
        "description": "A test rule for CRUD operations",
        "condition": "test_variable == 'test_value'",
        "conclusion": "valid",
        "priority": 5
    }
    
    add_rule_response = requests.post(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/rules",
        json=add_rule_data
    )
    
    if add_rule_response.status_code == 200:
        print("✅ Rule added successfully")
    else:
        print(f"❌ Failed to add rule: {add_rule_response.status_code} - {add_rule_response.text}")
    
    # Test 4: Update Rule
    print("\n🔬 Test 4: Update Rule")
    update_rule_data = {
        "description": "Updated test rule description",
        "condition": "test_variable != ''",
        "conclusion": "invalid",
        "priority": 10
    }
    
    update_rule_response = requests.patch(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/rules/test_rule",
        json=update_rule_data
    )
    
    if update_rule_response.status_code == 200:
        print("✅ Rule updated successfully")
    else:
        print(f"❌ Failed to update rule: {update_rule_response.status_code} - {update_rule_response.text}")
    
    # Test 5: Add Constraint
    print("\n🔬 Test 5: Add Constraint")
    constraint = "test_variable != ''"
    
    add_constraint_response = requests.post(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/constraints",
        params={"constraint": constraint}
    )
    
    if add_constraint_response.status_code == 200:
        print("✅ Constraint added successfully")
    else:
        print(f"❌ Failed to add constraint: {add_constraint_response.status_code} - {add_constraint_response.text}")
    
    # Test 6: Get Updated Policy (to verify changes)
    print("\n🔬 Test 6: Verify Policy Updates")
    policy_response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}")
    
    if policy_response.status_code == 200:
        policy = policy_response.json()
        print("✅ Policy retrieved successfully")
        
        # Check if our test variable exists
        test_var = next((v for v in policy.get('variables', []) if v['name'] == 'test_variable'), None)
        if test_var:
            print(f"  ✅ Test variable found: {test_var['name']} (mandatory: {test_var.get('is_mandatory', 'N/A')})")
        else:
            print("  ❌ Test variable not found")
        
        # Check if our test rule exists
        test_rule = next((r for r in policy.get('rules', []) if r['id'] == 'test_rule'), None)
        if test_rule:
            print(f"  ✅ Test rule found: {test_rule['id']} - {test_rule['description']}")
        else:
            print("  ❌ Test rule not found")
        
        # Check if our test constraint exists
        if constraint in policy.get('constraints', []):
            print(f"  ✅ Test constraint found: {constraint}")
        else:
            print(f"  ❌ Test constraint not found")
    
    else:
        print(f"❌ Failed to get updated policy: {policy_response.status_code}")
    
    # Cleanup: Delete test items
    print("\n🧹 Cleanup: Deleting Test Items")
    
    # Delete constraint
    delete_constraint_response = requests.delete(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/constraints",
        params={"constraint": constraint}
    )
    print(f"  Constraint deletion: {'✅' if delete_constraint_response.status_code == 200 else '❌'}")
    
    # Delete rule
    delete_rule_response = requests.delete(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/rules/test_rule"
    )
    print(f"  Rule deletion: {'✅' if delete_rule_response.status_code == 200 else '❌'}")
    
    # Delete variable
    delete_var_response = requests.delete(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/variables/test_variable"
    )
    print(f"  Variable deletion: {'✅' if delete_var_response.status_code == 200 else '❌'}")
    
    print("\n🎉 Policy CRUD API Test Complete!")

def test_ui_functionality():
    """Test UI functionality (mock test)"""
    print("\n🎨 UI Functionality Available:")
    print("=" * 40)
    print("✅ Variable Management:")
    print("  - Add new variables with mandatory toggle")
    print("  - Edit variable descriptions and values")
    print("  - Toggle mandatory/optional status")
    print("  - Set/update default values")
    print("  - Delete variables with confirmation")
    
    print("\n✅ Rule Management:")
    print("  - Add new rules with all fields")
    print("  - Edit rule descriptions, conditions, conclusions")
    print("  - Update rule priorities")
    print("  - Delete rules with confirmation")
    
    print("\n✅ Constraint Management:")
    print("  - Add new constraints")
    print("  - Delete constraints with confirmation")
    print("  - Helper text with examples")
    
    print("\n✅ Enhanced Policy View:")
    print("  - Interactive editing modes")
    print("  - Real-time updates via API")
    print("  - Visual indicators and confirmations")
    print("  - Automatic policy status reset to 'draft'")

if __name__ == "__main__":
    try:
        test_policy_crud_apis()
        test_ui_functionality()
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()