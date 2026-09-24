"""
Multi-source contact aggregator for Indian companies
Combines: RocketReach, Hunter, RapidAPI (Apollo), CSV dataset, PDF dataset, and web scraping
"""

import os
import csv
import json
import requests
import PyPDF2
from typing import List, Dict, Set
from dotenv import load_dotenv
from collections import defaultdict
import re

load_dotenv()

class ContactAggregator:
    def __init__(self):
        self.hunter_key = os.getenv('HUNTER_API_KEY')
        self.rapidapi_key = os.getenv('RAPIDAPI_KEY')
        self.rapidapi_host = os.getenv('RAPIDAPI_APOLLO_HOST')
        self.rocketreach_key = os.getenv('ROCKETREACH_API_KEY')
        self.indian_contacts = defaultdict(list)  # phone -> list of data
        self.phone_pattern = re.compile(r'^[6-9]\d{9}$')  # Indian phone format
        
    def validate_indian_phone(self, phone):
        """Validate Indian mobile number (10 digits, starts with 6-9)"""
        if not phone:
            return None
        # Clean phone number
        phone = re.sub(r'\D', '', str(phone))
        if self.phone_pattern.match(phone):
            return phone
        return None
    
    # ==================== CSV Dataset ====================
    def load_csv_dataset(self, filepath):
        """Extract phone numbers from globalb2bdataset.csv"""
        print(f"📊 Loading CSV dataset: {filepath}")
        count = 0
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Look for phone columns
                    for key in row.keys():
                        if 'phone' in key.lower() or 'mobile' in key.lower() or 'contact' in key.lower():
                            phone = self.validate_indian_phone(row[key])
                            if phone:
                                company = row.get('Company', row.get('company', 'Unknown'))
                                self.indian_contacts[phone].append({
                                    'source': 'CSV Dataset',
                                    'company': company,
                                    'data': row
                                })
                                count += 1
            print(f"✅ CSV: Found {count} Indian phone numbers")
        except Exception as e:
            print(f"❌ CSV Error: {e}")
        return count
    
    # ==================== PDF Dataset ====================
    def load_pdf_dataset(self, filepath):
        """Extract phone numbers from indian-corporates-database.pdf"""
        print(f"📄 Loading PDF dataset: {filepath}")
        count = 0
        try:
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                
                # Find Indian phone numbers in text
                phones = re.findall(r'[6-9]\d{9}', text)
                for phone in phones:
                    phone = self.validate_indian_phone(phone)
                    if phone and phone not in self.indian_contacts:
                        self.indian_contacts[phone].append({
                            'source': 'PDF Dataset',
                            'company': 'From PDF',
                            'data': None
                        })
                        count += 1
            print(f"✅ PDF: Found {count} Indian phone numbers")
        except Exception as e:
            print(f"❌ PDF Error: {e}")
        return count
    
    # ==================== RocketReach API ====================
    def search_rocketreach(self, query, limit=50):
        """Search RocketReach for Indian contacts"""
        print(f"🚀 Searching RocketReach: {query}")
        count = 0
        try:
            url = "https://api.rocketreach.co/v2/api/search/person"
            headers = {"Api-Key": self.rocketreach_key}
            
            params = {
                "keywords": query,
                "country": "India",
                "limit": limit
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for person in data.get('profiles', []):
                    phone = person.get('phone_number')
                    if phone:
                        phone = self.validate_indian_phone(phone)
                        if phone:
                            self.indian_contacts[phone].append({
                                'source': 'RocketReach',
                                'company': person.get('company', 'Unknown'),
                                'name': person.get('name', 'Unknown'),
                                'email': person.get('email', ''),
                                'title': person.get('title', '')
                            })
                            count += 1
            else:
                print(f"❌ RocketReach API Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ RocketReach Error: {e}")
        print(f"✅ RocketReach: Found {count} contacts")
        return count
    
    # ==================== Hunter.io API ====================
    def search_hunter(self, domain, limit=20):
        """Search Hunter.io for company email/phone"""
        print(f"🏹 Searching Hunter: {domain}")
        count = 0
        try:
            url = f"https://api.hunter.io/v2/domain-search?domain={domain}&limit={limit}"
            params = {"domain": domain, "limit": limit}
            headers = {"Authorization": f"Bearer {self.hunter_key}"}
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for person in data.get('emails', []):
                    phone = person.get('phone')
                    if phone:
                        phone = self.validate_indian_phone(phone)
                        if phone:
                            self.indian_contacts[phone].append({
                                'source': 'Hunter.io',
                                'company': person.get('company', 'Unknown'),
                                'name': person.get('first_name', ''),
                                'email': person.get('email', '')
                            })
                            count += 1
            else:
                print(f"⚠️ Hunter API Error: {response.status_code}")
        except Exception as e:
            print(f"❌ Hunter Error: {e}")
        print(f"✅ Hunter: Found {count} contacts")
        return count
    
    # ==================== RapidAPI (Apollo.io) ====================
    def search_apollo_rapidapi(self, query, limit=20):
        """Search Apollo.io via RapidAPI"""
        print(f"🔍 Searching Apollo.io (RapidAPI): {query}")
        count = 0
        try:
            url = "https://apollo-io-no-cookies-required.p.rapidapi.com/v1/people/search"
            
            payload = {
                "q_organization_name": query,
                "country": "India",
                "limit": limit
            }
            
            headers = {
                "x-rapidapi-key": self.rapidapi_key,
                "x-rapidapi-host": self.rapidapi_host,
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for person in data.get('contacts', []):
                    phone = person.get('phone_number') or person.get('mobile_number')
                    if phone:
                        phone = self.validate_indian_phone(phone)
                        if phone:
                            self.indian_contacts[phone].append({
                                'source': 'Apollo.io (RapidAPI)',
                                'company': person.get('company', 'Unknown'),
                                'name': person.get('name', ''),
                                'email': person.get('email', '')
                            })
                            count += 1
            else:
                print(f"⚠️ Apollo API Error: {response.status_code}")
        except Exception as e:
            print(f"❌ Apollo Error: {e}")
        print(f"✅ Apollo: Found {count} contacts")
        return count
    
    # ==================== Web Scraping ====================
    def web_scrape_indian_companies(self, company_list):
        """Basic web scraping for Indian company contacts"""
        print(f"🕷️ Web Scraping for {len(company_list)} companies...")
        count = 0
        # This would require company websites - placeholder implementation
        # In production, use: requests, BeautifulSoup4, Selenium
        print(f"✅ Web Scraping: Found {count} contacts (requires additional config)")
        return count
    
    # ==================== Consolidation ====================
    def get_all_indian_phones(self) -> List[str]:
        """Return sorted list of all unique Indian phone numbers"""
        return sorted(list(self.indian_contacts.keys()))
    
    def get_phone_details(self, phone: str) -> Dict:
        """Get all sources and details for a phone number"""
        return {
            'phone': phone,
            'sources': self.indian_contacts[phone],
            'source_count': len(set(s['source'] for s in self.indian_contacts[phone]))
        }
    
    def export_to_csv(self, filepath='indian_contacts_consolidated.csv'):
        """Export all contacts to CSV"""
        print(f"📥 Exporting to {filepath}")
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Phone', 'Company', 'Source', 'Name', 'Email', 'Title'])
                
                for phone in sorted(self.indian_contacts.keys()):
                    for contact in self.indian_contacts[phone]:
                        writer.writerow([
                            phone,
                            contact.get('company', ''),
                            contact.get('source', ''),
                            contact.get('name', ''),
                            contact.get('email', ''),
                            contact.get('title', '')
                        ])
            print(f"✅ Exported {len(self.indian_contacts)} unique phone numbers")
        except Exception as e:
            print(f"❌ Export Error: {e}")
    
    def print_summary(self):
        """Print summary statistics"""
        print("\n" + "="*60)
        print("📊 CONTACT AGGREGATION SUMMARY")
        print("="*60)
        print(f"Total Unique Indian Phone Numbers: {len(self.indian_contacts)}")
        
        # Source breakdown
        source_count = defaultdict(int)
        for phone, contacts in self.indian_contacts.items():
            for contact in contacts:
                source_count[contact['source']] += 1
        
        print("\n📍 Breakdown by Source:")
        for source, count in sorted(source_count.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {source}: {count}")
        print("="*60 + "\n")


def main():
    aggregator = ContactAggregator()
    
    # 1. Load CSV Dataset
    aggregator.load_csv_dataset('globalb2bdataset.csv')
    
    # 2. Load PDF Dataset
    aggregator.load_pdf_dataset('171399177-Indian-corporates-database-Sample-data-of-professionals-with-mobile-and-email-id.pdf')
    
    # 3. Search RocketReach
    aggregator.search_rocketreach("India companies", limit=100)
    
    # 4. Search Hunter
    aggregator.search_hunter("example.com", limit=50)
    
    # 5. Search Apollo via RapidAPI
    aggregator.search_apollo_rapidapi("Indian", limit=50)
    
    # 6. Print Summary
    aggregator.print_summary()
    
    # 7. Get All Phone Numbers
    all_phones = aggregator.get_all_indian_phones()
    print(f"\n📱 ALL {len(all_phones)} INDIAN PHONE NUMBERS:")
    print("-" * 60)
    for phone in all_phones:
        details = aggregator.get_phone_details(phone)
        sources = ", ".join([s['source'] for s in details['sources']])
        print(f"{phone} | Sources: {sources}")
    
    # 8. Export to CSV
    aggregator.export_to_csv()


if __name__ == "__main__":
    main()
