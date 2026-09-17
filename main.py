import os
import datetime
import smtplib
import requests
from bs4 import BeautifulSoup
from email.message import EmailMessage
from supabase import create_client, Client

# ==========================================
# 1. INITIALIZE CLIENTS & ENV VARIABLES
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

if not SUPABASE_URL or not SUPABASE_KEY or not GMAIL_USER or not GMAIL_APP_PASSWORD:
    raise ValueError("Missing essential environment variables in GitHub Secrets.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


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
            cols = [col.text.strip().replace("\n", " ") for col in row.find_all("td")]
            if len(cols) >= 10:
                company_name = cols[1].strip()
                open_date = cols[8].strip()   # Standard date format YYYY-MM-DD
                close_date = cols[9].strip()  # Standard date format YYYY-MM-DD
                
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
# 4. EMAIL DISPATCH SYSTEM (GMAIL SMTP)
# ==========================================
def send_broadcast_email(subscribers, subject, content_html):
    """Broadcasts notification emails using Gmail SMTP."""
    clean_subject = subject.replace("\n", " ").replace("\r", " ").strip()
    
    if not subscribers:
        print("No subscribers to email.")
        return

    try:
        # Reuse a single SMTP connection for the entire subscriber list
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            
            for recipient in subscribers:
                msg = EmailMessage()
                msg["Subject"] = clean_subject
                msg["From"] = f"IPO Alert Bot <{GMAIL_USER}>"
                msg["To"] = recipient
                msg.add_alternative(content_html, subtype="html")
                
                smtp.send_message(msg)
                print(f"Delivered email to: {recipient}")
                
    except Exception as e:
        print(f"Gmail SMTP dispatch error: {e}")


def run_daily_notifications():
    """Checks date matches for today and dispatches alerts in English & Nepali."""
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
        clean_company = str(ipo['company_name']).replace('\n', ' ').strip()
        subject = f"🚀 IPO OPEN TODAY: {clean_company} | आजदेखि IPO खुल्यो!"
        body = f"""
        <div style="font-family: sans-serif; padding: 20px; color: #333; line-height: 1.6;">
            <h2 style="color: #2b6cb0;">🚀 IPO Subscription is Now Open!</h2>
            <h3 style="color: #4a5568; margin-top: -10px;">आजदेखि IPO निष्कासन तथा बिक्री खुला भएको छ!</h3>
            
            <table style="width: 100%; max-width: 500px; border-collapse: collapse; margin: 20px 0;">
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 8px 0;"><strong>Company (कम्पनी):</strong></td>
                    <td style="padding: 8px 0;">{clean_company}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 8px 0;"><strong>Opening Date (भर्ने सुरु मिति):</strong></td>
                    <td style="padding: 8px 0;">{ipo['open_date']}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 8px 0;"><strong>Closing Date (भर्ने अन्तिम मिति):</strong></td>
                    <td style="padding: 8px 0;">{ipo['close_date']}</td>
                </tr>
            </table>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0;">
            <p>Don't forget to submit your application today via MeroShare!</p>
            <p style="font-weight: bold; color: #2d3748;">आजै मेरोसेयर (MeroShare) मार्फत आफ्नो आवेदन पेस गर्न नबिर्सनुहोला!</p>
        </div>
        """
        print(f"Sending opening alert for {clean_company}...")
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
        clean_company = str(ipo['company_name']).replace('\n', ' ').strip()
        subject = f"⚠️ LAST CHANCE: {clean_company} IPO Closes Today! | आज भर्ने अन्तिम दिन!"
        body = f"""
        <div style="font-family: sans-serif; padding: 20px; color: #333; line-height: 1.6;">
            <h2 style="color: #c53030;">⚠️ LAST CHANCE: IPO Closes Today!</h2>
            <h3 style="color: #742a2a; margin-top: -10px;">आज IPO आवेदन दिने अन्तिम दिन हो!</h3>
            
            <p><strong>Company (कम्पनी):</strong> {clean_company}</p>
            <p>This is your final reminder that applications for <strong>{clean_company}</strong> close today ({ipo['close_date']}).</p>
            <p style="font-weight: bold; color: #c53030;"><strong>{clean_company}</strong> को IPO मा आवेदन दिने आज अन्तिम दिन भएकाले तुरुन्त MeroShare बाट भर्नुहोस्।</p>
        </div>
        """
        print(f"Sending closing alert for {clean_company}...")
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
