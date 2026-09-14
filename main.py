import os
import datetime
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import resend

# ==========================================
# 1. INITIALIZE CLIENTS & ENV VARIABLES
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")

if not SUPABASE_URL or not SUPABASE_KEY or not RESEND_API_KEY:
    raise ValueError("Missing essential environment variables in GitHub Secrets.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
resend.api_key = RESEND_API_KEY


# ==========================================
# 2. SCRAPER ENGINE (ShareSansar Target)
# ==========================================
def scrape_upcoming_ipos():
    """Scrapes upcoming IPOs from target portal."""
    print("Scraping target financial portal...")
    url = "https://www.sharesansar.com/upcoming-issue"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    scraped_ipos = []
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch webpage: Status {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        
        if not table:
            print("No IPO table found on page.")
            return []
            
        rows = table.find_all("tr")[1:]  # Skip table header row
        
        for row in rows:
            cols = [col.text.strip() for col in row.find_all("td")]
            # Extract Company Name, Opening Date, and Closing Date
            if len(cols) >= 10:
                company_name = cols[1]
                open_date = cols[8]   # Standard date format YYYY-MM-DD
                close_date = cols[9]  # Standard date format YYYY-MM-DD
                
                if open_date and close_date and len(open_date) == 10:
                    scraped_ipos.append({
                        "company_name": company_name,
                        "open_date": open_date,
                        "close_date": close_date
                    })
                    
    except Exception as e:
        print(f"Scraper error encountered: {e}")
        
    print(f"Scraped {len(scraped_ipos)} total IPO entries.")
    return scraped_ipos


# ==========================================
# 3. DATABASE SYNC
# ==========================================
def sync_ipos_to_supabase(scraped_ipos):
    """Inserts newly scraped IPOs into Supabase if they don't already exist."""
    for ipo in scraped_ipos:
        existing = supabase.table("ipos") \
            .select("id") \
            .eq("company_name", ipo["company_name"]) \
            .eq("open_date", ipo["open_date"]) \
            .execute()
            
        if not existing.data:
            supabase.table("ipos").insert({
                "company_name": ipo["company_name"],
                "open_date": ipo["open_date"],
                "close_date": ipo["close_date"],
                "open_email_sent": False,
                "close_email_sent": False
            }).execute()
            print(f"Stored new IPO: {ipo['company_name']}")


# ==========================================
# 4. EMAIL DISPATCH SYSTEM
# ==========================================
def send_broadcast_email(subscribers, subject, content_html):
    """Broadcasts notification emails using Resend."""
    try:
        response = resend.Emails.send({
            "from": SENDER_EMAIL,
            "to": subscribers,
            "subject": subject,
            "html": content_html
        })
        print(f"Dispatched email broadcast. Resend ID: {response.get('id')}")
    except Exception as e:
        print(f"Resend dispatch error: {e}")


def run_daily_notifications():
    """Checks date matches for today and dispatches alerts."""
    today = datetime.date.today().isoformat()
    print(f"Checking schedules against current date: {today}")
    
    # Fetch subscriber list
    sub_response = supabase.table("subscribers").select("email").execute()
    subscribers = [row["email"] for row in sub_response.data]
    
    if not subscribers:
        print("No subscribers found in database. Exiting.")
        return

    # Check for IPOs Opening Today
    open_ipos = supabase.table("ipos") \
        .select("*") \
        .eq("open_date", today) \
        .eq("open_email_sent", False) \
        .execute()
        
    for ipo in open_ipos.data:
        subject = f"🚀 IPO OPEN TODAY: {ipo['company_name']}"
        body = f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>IPO Subscription is Now Open!</h2>
            <p><strong>Company:</strong> {ipo['company_name']}</p>
            <p><strong>Opening Date:</strong> {ipo['open_date']}</p>
            <p><strong>Closing Date:</strong> {ipo['close_date']}</p>
            <hr>
            <p>Don't forget to submit your application today!</p>
        </div>
        """
        print(f"Sending opening alert for {ipo['company_name']}...")
        send_broadcast_email(subscribers, subject, body)
        
        supabase.table("ipos") \
            .update({"open_email_sent": True}) \
            .eq("id", ipo["id"]) \
            .execute()

    # Check for IPOs Closing Today
    close_ipos = supabase.table("ipos") \
        .select("*") \
        .eq("close_date", today) \
        .eq("close_email_sent", False) \
        .execute()
        
    for ipo in close_ipos.data:
        subject = f"⚠️ LAST CHANCE: {ipo['company_name']} IPO Closes Today!"
        body = f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>IPO Closes Today!</h2>
            <p><strong>Company:</strong> {ipo['company_name']}</p>
            <p>This is your final reminder that applications for {ipo['company_name']} close today ({ipo['close_date']}).</p>
        </div>
        """
        print(f"Sending closing alert for {ipo['company_name']}...")
        send_broadcast_email(subscribers, subject, body)
        
        supabase.table("ipos") \
            .update({"close_email_sent": True}) \
            .eq("id", ipo["id"]) \
            .execute()


# ==========================================
# 5. EXECUTION ENTRYPOINT
# ==========================================
if __name__ == "__main__":
    ipos = scrape_upcoming_ipos()
    if ipos:
        sync_ipos_to_supabase(ipos)
    run_daily_notifications()
