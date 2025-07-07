# migrate.py - Render.com Database Migration Script

import os
import sys
from flask import Flask
from models import db, init_database, get_database_status, configure_for_render

def create_app():
    """Create Flask app with Render configuration"""
    app = Flask(__name__)
    
    # Configure for Render
    render_config = configure_for_render()
    app.config.update(render_config)
    
    # Initialize database
    db.init_app(app)
    
    return app

def run_migration():
    """Run database migration for Render deployment"""
    print("🚀 Starting Gopher Minigolf Database Migration...")
    
    app = create_app()
    
    with app.app_context():
        try:
            # Step 1: Check current status
            print("\n1️⃣ Checking database status...")
            status = get_database_status()
            
            if status['status'] == 'healthy':
                print("✅ Database already set up and healthy!")
                print(f"📊 Current data: {status}")
                return True
            
            # Step 2: Initialize database
            print("\n2️⃣ Initializing database...")
            if init_database():
                print("✅ Database initialization successful!")
            else:
                print("❌ Database initialization failed!")
                return False
            
            # Step 3: Verify setup
            print("\n3️⃣ Verifying setup...")
            final_status = get_database_status()
            
            if final_status['status'] == 'healthy':
                print("🎉 Migration completed successfully!")
                print(f"📊 Final status: {final_status}")
                return True
            else:
                print(f"❌ Migration verification failed: {final_status}")
                return False
                
        except Exception as e:
            print(f"💀 Migration failed with error: {e}")
            return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)