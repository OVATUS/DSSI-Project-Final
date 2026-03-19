"""
APScheduler setup for automated task reminders
Runs in the background and calls the send_task_reminders view every hour
"""

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
import requests
import logging

logger = logging.getLogger(__name__)

scheduler = None


def start_scheduler():
    """Start the background scheduler for automated reminders"""
    global scheduler
    
    # Avoid starting scheduler multiple times
    if scheduler is not None and scheduler.running:
        return
    
    try:
        scheduler = BackgroundScheduler()
        
        # Schedule the reminder task to run every 1 hour
        scheduler.add_job(
            trigger_reminders,
            'interval',
            hours=1,
            id='send_task_reminders',
            name='Send Task Reminders',
            replace_existing=True,
            max_instances=1
        )
        
        scheduler.start()
        logger.info("✅ APScheduler started successfully - Task reminders scheduled every 1 hour")
        
    except Exception as e:
        logger.error(f"❌ Error starting APScheduler: {e}")


def stop_scheduler():
    """Stop the background scheduler"""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("⛔ APScheduler stopped")


def trigger_reminders():
    """
    Triggered by scheduler - makes HTTP POST request to the reminder view
    This avoids importing Django views directly into the scheduler
    """
    try:
        # Use localhost to call the API endpoint
        # We'll use Django's test client alternative or direct HTTP
        from django.test import Client
        from django.contrib.auth import get_user_model
        
        # Create a fake POST request to trigger reminders
        # Since this is internal, we can use Django's test client
        client = Client()
        
        # Call the REST API endpoint (will be added to urls.py)
        response = client.post('/board/api/send-reminders/')
        
        if response.status_code == 200:
            logger.info("✅ Reminders sent successfully via scheduler")
        else:
            logger.warning(f"⚠️ Reminder endpoint returned status {response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ Error triggering reminders: {e}")
