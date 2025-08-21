#!/usr/bin/env python3
"""
Test complete policy editing functionality with specific policy ID
"""

import requests
import json
import time

# Configuration
API_BASE_URL = "http://localhost:9066"
API_V1_PREFIX = "/api/v1"
POLICY_ID = "adf95535-0103-485f-a202-87cdac80e78e"

def print_separator(title):
    print(f"\n{'='*60}")
    print(f"🔬 {title}")
    print('='*60)

def print_step(step_num, description):
    print(f"\n📋 Step {step_num}: {description}")
    print("-" * 50)

def get_policy():
    """Get current policy state"""
    response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}")
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Failed to get policy: {response.status_code} - {response.text}")
        return None

def print_policy_summary(policy):
    """Print a summary of the policy"""
    if not policy:
        return
    
    print(f"📊 Policy: {policy.get('name', 'N/A')} (Status: {policy.get('status', 'N/A')})")
    
    variables = policy.get('variables', [])
    print(f"🔢 Variables ({len(variables)}):")
    for var in variables:
        mandatory = "🔴 MANDATORY" if var.get('is_mandatory', True) else "🟢 OPTIONAL"
        default = f" (default: {var.get('default_value')})" if var.get('default_value') else ""
        print(f"  - {var['name']} ({var['type']}) - {mandatory}{default}")
    
    rules = policy.get('rules', [])
    print(f"⚖️ Rules ({len(rules)}):")
    for rule in rules:
        emoji = "✅" if rule.get('conclusion') == 'valid' else "❌"
        print(f"  - {emoji} {rule['id']}: {rule['description']}")
    
    constraints = policy.get('constraints', [])
    print(f"🔒 Constraints ({len(constraints)}):")
    for constraint in constraints:
        print(f"  - {constraint}")

def test_complete_policy_editing():
    """Test all policy editing operations"""
    
    print_separator("Testing Complete Policy CRUD Operations")
    
    # Get initial policy state
    print_step(1, "Get Initial Policy State")
    initial_policy = get_policy()
    if not initial_policy:
        return
    
    print("✅ Successfully retrieved policy")
    print_policy_summary(initial_policy)
    
    # Test Variable Operations
    print_step(2, "Test Variable Operations")
    
    # Add a new variable
    print("➕ Adding new test variable...")
    add_var_data = {
        "name": "test_editing_var",
        "type": "boolean",
        "description": "Test variable for CRUD operations demonstration",
        "is_mandatory": False,
        "default_value": "true"
    }
    
    add_var_response = requests.post(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/variables",
        json=add_var_data
    )
    
    if add_var_response.status_code == 200:
        print("✅ Variable added successfully")
    else:
        print(f"❌ Failed to add variable: {add_var_response.status_code} - {add_var_response.text}")
    
    time.sleep(1)  # Brief pause between operations
    
    # Update variable to make it mandatory
    print("🔄 Updating variable to mandatory...")
    update_var_data = {
        "variable_name": "test_editing_var",
        "is_mandatory": True,
        "default_value": ""  # Remove default when making mandatory
    }
    
    update_var_response = requests.patch(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/variables/test_editing_var",
        json=update_var_data
    )
    
    if update_var_response.status_code == 200:
        print("✅ Variable updated to mandatory")
    else:
        print(f"❌ Failed to update variable: {update_var_response.status_code} - {update_var_response.text}")
    
    # Test existing variable modification (if exists)
    current_policy = get_policy()
    if current_policy and current_policy.get('variables'):
        existing_var = current_policy['variables'][0]  # Get first variable
        print(f"🔄 Testing toggle of existing variable '{existing_var['name']}'...")
        
        # Toggle its mandatory status
        new_mandatory_status = not existing_var.get('is_mandatory', True)
        toggle_data = {
            "variable_name": existing_var['name'],
            "is_mandatory": new_mandatory_status
        }
        
        toggle_response = requests.patch(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/variables/{existing_var['name']}",
            json=toggle_data
        )
        
        if toggle_response.status_code == 200:
            print(f"✅ Toggled '{existing_var['name']}' mandatory status to {new_mandatory_status}")
        else:
            print(f"❌ Failed to toggle variable: {toggle_response.status_code}")
    
    # Test Rule Operations
    print_step(3, "Test Rule Operations")
    
    # Add a new rule
    print("➕ Adding new test rule...")
    add_rule_data = {
        "id": "test_editing_rule",
        "description": "Test rule for CRUD operations demonstration",
        "condition": "test_editing_var == true",
        "conclusion": "valid",
        "priority": 999
    }
    
    add_rule_response = requests.post(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/rules",
        json=add_rule_data
    )
    
    if add_rule_response.status_code == 200:
        print("✅ Rule added successfully")
    else:
        print(f"❌ Failed to add rule: {add_rule_response.status_code} - {add_rule_response.text}")
    
    time.sleep(1)
    
    # Update the rule
    print("🔄 Updating rule...")
    update_rule_data = {
        "description": "Updated test rule description - now checks for false",
        "condition": "test_editing_var == false",
        "conclusion": "invalid",
        "priority": 1
    }
    
    update_rule_response = requests.patch(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/rules/test_editing_rule",
        json=update_rule_data
    )
    
    if update_rule_response.status_code == 200:
        print("✅ Rule updated successfully")
    else:
        print(f"❌ Failed to update rule: {update_rule_response.status_code} - {update_rule_response.text}")
    
    # Test Constraint Operations
    print_step(4, "Test Constraint Operations")
    
    # Add a new constraint
    print("➕ Adding new constraint...")
    test_constraint = "test_editing_var != null"
    
    add_constraint_response = requests.post(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/constraints",
        params={"constraint": test_constraint}
    )
    
    if add_constraint_response.status_code == 200:
        print("✅ Constraint added successfully")
    else:
        print(f"❌ Failed to add constraint: {add_constraint_response.status_code} - {add_constraint_response.text}")
    
    # Show final state
    print_step(5, "Final Policy State After All Modifications")
    final_policy = get_policy()
    if final_policy:
        print("✅ Retrieved final policy state")
        print_policy_summary(final_policy)
        
        # Compare with initial state
        print(f"\n📊 Summary of Changes:")
        initial_var_count = len(initial_policy.get('variables', []))
        final_var_count = len(final_policy.get('variables', []))
        print(f"  Variables: {initial_var_count} → {final_var_count} (+{final_var_count - initial_var_count})")
        
        initial_rule_count = len(initial_policy.get('rules', []))
        final_rule_count = len(final_policy.get('rules', []))
        print(f"  Rules: {initial_rule_count} → {final_rule_count} (+{final_rule_count - initial_rule_count})")
        
        initial_constraint_count = len(initial_policy.get('constraints', []))
        final_constraint_count = len(final_policy.get('constraints', []))
        print(f"  Constraints: {initial_constraint_count} → {final_constraint_count} (+{final_constraint_count - initial_constraint_count})")
        
        print(f"  Status: {initial_policy.get('status')} → {final_policy.get('status')}")
    
    # Cleanup
    print_step(6, "Cleanup Test Items")
    
    print("🧹 Cleaning up test items...")
    
    # Delete test constraint
    delete_constraint_response = requests.delete(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/constraints",
        params={"constraint": test_constraint}
    )
    constraint_status = "✅" if delete_constraint_response.status_code == 200 else "❌"
    print(f"  Constraint deletion: {constraint_status}")
    
    # Delete test rule
    delete_rule_response = requests.delete(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/rules/test_editing_rule"
    )
    rule_status = "✅" if delete_rule_response.status_code == 200 else "❌"
    print(f"  Rule deletion: {rule_status}")
    
    # Delete test variable
    delete_var_response = requests.delete(
        f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/variables/test_editing_var"
    )
    var_status = "✅" if delete_var_response.status_code == 200 else "❌"
    print(f"  Variable deletion: {var_status}")
    
    print(f"\n🎉 Policy Editing Test Complete!")
    print(f"📋 Tested Policy ID: {POLICY_ID}")

def test_streamlit_ui_features():
    """Demonstrate available Streamlit UI features"""
    print_separator("Available Streamlit UI Features")
    
    print("🎨 **Interactive Policy Editor Available At:** http://localhost:8501")
    print("\n📝 **Variable Management:**")
    print("  • Add new variables with all field types (string, number, boolean, enum, date)")
    print("  • Toggle mandatory/optional status with real-time updates")
    print("  • Set and modify default values for optional variables")
    print("  • Edit descriptions and possible values inline")
    print("  • Delete variables with double-click confirmation")
    
    print("\n⚖️ **Rule Management:**")
    print("  • Add new rules with condition builder")
    print("  • Edit rule descriptions, conditions, and conclusions")
    print("  • Adjust rule priorities with number input")
    print("  • Visual indicators for valid (✅) vs invalid (❌) rules")
    print("  • Delete rules with confirmation dialog")
    
    print("\n🔒 **Constraint Management:**")
    print("  • Add global constraints with example suggestions")
    print("  • View constraints in formatted code blocks")
    print("  • Delete constraints with confirmation")
    
    print("\n🔄 **Real-time Features:**")
    print("  • All changes update the policy immediately via API")
    print("  • Policy status automatically resets to 'draft' when edited")
    print("  • Success/error notifications for all operations")
    print("  • Session state management for edit modes")

if __name__ == "__main__":
    try:
        test_complete_policy_editing()
        test_streamlit_ui_features()
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()