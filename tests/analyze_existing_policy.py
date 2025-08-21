#!/usr/bin/env python3
"""
Analyze the existing policy and demonstrate what changes are possible
"""

import requests
import json

# Configuration
API_BASE_URL = "http://localhost:9066"
API_V1_PREFIX = "/api/v1"
POLICY_ID = "adf95535-0103-485f-a202-87cdac80e78e"

def get_policy():
    """Get the policy"""
    response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}")
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Failed to get policy: {response.status_code}")
        return None

def analyze_policy():
    """Analyze the existing policy structure"""
    print("🔍 Analyzing Your Expense Reimbursements Policy")
    print("=" * 60)
    
    policy = get_policy()
    if not policy:
        return
    
    print(f"📋 Policy: {policy['name']}")
    print(f"🏢 Domain: {policy['domain']}")
    print(f"📊 Status: {policy['status']}")
    print(f"📝 Description: {policy['description']}")
    
    print(f"\n🔢 Variables Analysis ({len(policy.get('variables', []))} total):")
    mandatory_vars = []
    optional_vars = []
    
    for var in policy.get('variables', []):
        is_mandatory = var.get('is_mandatory', True)
        has_default = 'default_value' in var
        
        var_info = {
            'name': var['name'],
            'type': var['type'],
            'description': var['description'],
            'is_mandatory': is_mandatory,
            'has_default': has_default,
            'possible_values': var.get('possible_values', [])
        }
        
        if is_mandatory:
            mandatory_vars.append(var_info)
        else:
            optional_vars.append(var_info)
    
    print(f"\n🔴 Mandatory Variables ({len(mandatory_vars)}):")
    for var in mandatory_vars:
        pv_info = f" (values: {', '.join(var['possible_values'])})" if var['possible_values'] else ""
        print(f"  • {var['name']} ({var['type']}): {var['description']}{pv_info}")
    
    print(f"\n🟢 Optional Variables ({len(optional_vars)}):")
    for var in optional_vars:
        pv_info = f" (values: {', '.join(var['possible_values'])})" if var['possible_values'] else ""
        default_info = " [HAS DEFAULT]" if var['has_default'] else " [NO DEFAULT → SKIP RULE]"
        print(f"  • {var['name']} ({var['type']}): {var['description']}{pv_info}{default_info}")
    
    print(f"\n⚖️ Rules Analysis ({len(policy.get('rules', []))} total):")
    valid_rules = [r for r in policy['rules'] if r['conclusion'] == 'valid']
    invalid_rules = [r for r in policy['rules'] if r['conclusion'] == 'invalid']
    
    print(f"\n✅ Validity Rules ({len(valid_rules)}) - Define when reimbursement is allowed:")
    for rule in valid_rules:
        priority = rule.get('priority', 'N/A')
        print(f"  • [{priority}] {rule['id']}: {rule['description']}")
        print(f"    Condition: {rule['condition']}")
    
    print(f"\n❌ Violation Rules ({len(invalid_rules)}) - Define when reimbursement is denied:")
    for rule in invalid_rules:
        priority = rule.get('priority', 'N/A')
        print(f"  • [{priority}] {rule['id']}: {rule['description']}")
        print(f"    Condition: {rule['condition']}")
    
    print(f"\n🔒 Global Constraints ({len(policy.get('constraints', []))}):")
    for constraint in policy.get('constraints', []):
        print(f"  • {constraint}")
    
    print(f"\n💡 Policy Editing Capabilities:")
    print("With the new system, you can now:")
    print("✅ Toggle any variable between mandatory/optional")
    print("✅ Add default values to optional variables") 
    print("✅ Add new variables with any type")
    print("✅ Add new rules with custom conditions")
    print("✅ Add new global constraints")
    print("✅ Edit existing rule descriptions and conditions")
    print("✅ Delete variables, rules, or constraints")
    
    print(f"\n🎯 Suggested Modifications for Testing:")
    print("1. Make 'flight_type' mandatory (currently optional)")
    print("2. Add default value 'false' to 'has_cfo_approval'")
    print("3. Add a new variable: 'receipt_quality' (enum: good/poor)")
    print("4. Add a new rule: 'Poor quality receipts require manual review'")
    print("5. Add constraint: 'submission_days <= 30'")
    
    print(f"\n🔧 Next Steps:")
    print("• Visit Streamlit UI: http://localhost:8501")
    print("• Navigate to 'Policy Editor' and select this policy")
    print("• Use the interactive toggles and forms to make changes")
    print("• All changes will be saved immediately via API")

def demonstrate_manual_changes():
    """Show what specific changes would look like"""
    print(f"\n🛠️  Manual Change Examples:")
    print("=" * 40)
    
    policy = get_policy()
    if not policy:
        return
    
    print("Example 1 - Toggle 'flight_type' to mandatory:")
    flight_var = next((v for v in policy['variables'] if v['name'] == 'flight_type'), None)
    if flight_var:
        print(f"  Current: {flight_var['name']} - {'🔴 MANDATORY' if flight_var.get('is_mandatory', True) else '🟢 OPTIONAL'}")
        print(f"  After toggle: flight_type - 🔴 MANDATORY")
        print(f"  Impact: System will require flight type for all expense claims")
    
    print(f"\nExample 2 - Add default to 'has_cfo_approval':")
    cfo_var = next((v for v in policy['variables'] if v['name'] == 'has_cfo_approval'), None)
    if cfo_var:
        current_default = cfo_var.get('default_value', 'None')
        print(f"  Current default: {current_default}")
        print(f"  After change: 'false'")
        print(f"  Impact: When CFO approval status can't be determined, assume no approval")
    
    print(f"\nExample 3 - New Variable Addition:")
    print(f"  Name: receipt_quality")
    print(f"  Type: enum")
    print(f"  Values: ['excellent', 'good', 'poor', 'illegible']")
    print(f"  Mandatory: false")
    print(f"  Default: 'good'")
    print(f"  Impact: Enables quality-based approval rules")

if __name__ == "__main__":
    analyze_policy()
    demonstrate_manual_changes()