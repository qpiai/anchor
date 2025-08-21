#!/usr/bin/env python3
"""
Database enum migration script to fix case mismatch
Changes verificationresult enum from UPPERCASE to lowercase values
"""

import sys
import os
sys.path.append('.')

from app.core.database import engine
from sqlalchemy import text

def migrate_enum():
    """Migrate verificationresult enum from uppercase to lowercase values"""
    
    print("🔧 Starting verificationresult enum migration...")
    
    try:
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                print("Step 1: Creating new enum with lowercase values...")
                conn.execute(text("""
                    CREATE TYPE verificationresult_new AS ENUM (
                        'valid',
                        'invalid', 
                        'error',
                        'needs_clarification'
                    )
                """))
                
                print("Step 2: Adding temporary column with new enum...")
                conn.execute(text("""
                    ALTER TABLE verifications 
                    ADD COLUMN verification_result_new verificationresult_new
                """))
                
                print("Step 3: Migrating data with case conversion...")
                conn.execute(text("""
                    UPDATE verifications 
                    SET verification_result_new = CASE 
                        WHEN verification_result = 'VALID' THEN 'valid'::verificationresult_new
                        WHEN verification_result = 'INVALID' THEN 'invalid'::verificationresult_new
                        WHEN verification_result = 'ERROR' THEN 'error'::verificationresult_new
                        WHEN verification_result = 'NEEDS_CLARIFICATION' THEN 'needs_clarification'::verificationresult_new
                    END
                """))
                
                print("Step 4: Dropping old column...")
                conn.execute(text("""
                    ALTER TABLE verifications 
                    DROP COLUMN verification_result
                """))
                
                print("Step 5: Renaming new column...")
                conn.execute(text("""
                    ALTER TABLE verifications 
                    RENAME COLUMN verification_result_new TO verification_result
                """))
                
                print("Step 6: Dropping old enum type...")
                conn.execute(text("""
                    DROP TYPE verificationresult
                """))
                
                print("Step 7: Renaming new enum type...")
                conn.execute(text("""
                    ALTER TYPE verificationresult_new RENAME TO verificationresult
                """))
                
                # Commit transaction
                trans.commit()
                print("✅ Enum migration completed successfully!")
                
                # Verify the migration
                result = conn.execute(text("SELECT unnest(enum_range(NULL::verificationresult))"))
                values = [row[0] for row in result]
                print("New enum values:")
                for value in values:
                    print(f"  - \"{value}\"")
                    
            except Exception as e:
                print(f"❌ Migration failed, rolling back: {e}")
                trans.rollback()
                raise
                
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False
        
    return True

if __name__ == "__main__":
    success = migrate_enum()
    if success:
        print("🎉 Database enum migration completed successfully!")
    else:
        print("💥 Database enum migration failed!")
        sys.exit(1)