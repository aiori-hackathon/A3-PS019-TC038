"""Seeded synthetic value generators. Every value is invented; no real people."""
from __future__ import annotations

import random
import string
from datetime import date, datetime, timedelta

from .validators import STATE_CODES, gstin_check_char, luhn_check_digit, verhoeff_check_digit

FIRST = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan", "Ananya",
         "Diya", "Saanvi", "Aadhya", "Myra", "Pari", "Anika", "Navya", "Kavya", "Riya", "Rahul", "Priya", "Amit",
         "Sneha", "Rohit", "Pooja", "Vikram", "Neha", "Karan", "Meena", "Imran", "Zainab", "Harpreet", "Joseph",
         "Lakshmi", "Suresh", "Deepika", "Farhan", "Shreya", "Manish"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Patel", "Shah", "Gupta", "Singh", "Kumar", "Mehta", "Joshi",
        "Menon", "Pillai", "Rao", "Banerjee", "Chatterjee", "Das", "Khan", "Ahmed", "Fernandes", "Kulkarni", "Patil",
        "Desai", "Bhat", "Hegde", "Gill", "Kaur", "Thomas", "Mathew", "Agarwal", "Jain", "Mishra", "Pandey", "Yadav"]
CITIES = [("Mumbai", "Maharashtra", "400"), ("Pune", "Maharashtra", "411"), ("Bengaluru", "Karnataka", "560"),
          ("Chennai", "Tamil Nadu", "600"), ("Hyderabad", "Telangana", "500"), ("Kolkata", "West Bengal", "700"),
          ("Delhi", "Delhi", "110"), ("Ahmedabad", "Gujarat", "380"), ("Jaipur", "Rajasthan", "302"),
          ("Lucknow", "Uttar Pradesh", "226"), ("Kochi", "Kerala", "682"), ("Indore", "Madhya Pradesh", "452")]
CITY_COORDS = {"Mumbai": (19.07, 72.87), "Pune": (18.52, 73.85), "Bengaluru": (12.97, 77.59), "Chennai": (13.08, 80.27),
               "Hyderabad": (17.38, 78.48), "Kolkata": (22.57, 88.36), "Delhi": (28.61, 77.20), "Ahmedabad": (23.02, 72.57),
               "Jaipur": (26.91, 75.78), "Lucknow": (26.84, 80.94), "Kochi": (9.93, 76.26), "Indore": (22.71, 75.85)}
STREETS = ["MG Road", "Linking Road", "4th Cross", "Station Road", "Nehru Nagar", "Gandhi Marg", "Park Street",
           "Sector 21", "Shivaji Nagar", "Anna Salai", "Banjara Hills Road No 3", "Koramangala 5th Block"]
DOMAINS = ["gmail.com", "yahoo.co.in", "outlook.com", "rediffmail.com", "hotmail.com", "example.in"]
UPI = ["okaxis", "oksbi", "ybl", "paytm", "okhdfcbank", "ibl", "apl"]
BANKS = ["HDFC", "ICIC", "SBIN", "UTIB", "KKBK", "PUNB", "BARB", "CNRB"]
GENDERS = ["Male", "Female", "Male", "Female", "Other"]
JOBS = ["Software Engineer", "Teacher", "Accountant", "Nurse", "Sales Executive", "Business Owner", "Student",
        "Doctor", "Civil Engineer", "Designer", "Consultant", "Driver"]


class Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)

    def choice(self, xs):
        return self.r.choice(xs)

    def digits(self, n: int, first: str = "0123456789") -> str:
        return self.r.choice(first) + "".join(self.r.choice(string.digits) for _ in range(n - 1))

    def name(self) -> str:
        return f"{self.choice(FIRST)} {self.choice(LAST)}"

    def email(self, name: str | None = None) -> str:
        name = name or self.name()
        first, last = name.lower().split()[:2]
        style = self.r.randint(0, 3)
        local = [f"{first}.{last}", f"{first}{self.r.randint(1, 99)}", f"{first[0]}{last}", f"{last}.{first}{self.r.randint(70, 99)}"][style]
        return f"{local}@{self.choice(DOMAINS)}"

    def mobile(self, fmt: str = "mixed") -> str:
        n = self.digits(10, "6789")
        style = self.r.randint(0, 4) if fmt == "mixed" else 0
        return [n, f"+91 {n[:5]} {n[5:]}", f"0{n}", f"+91-{n}", f"{n[:5]}-{n[5:]}"][style]

    def aadhaar(self, spaced: bool = False) -> str:
        base = self.digits(11, "23456789")
        v = base + verhoeff_check_digit(base)
        return f"{v[:4]} {v[4:8]} {v[8:]}" if spaced else v

    def pan(self, holder: str = "P") -> str:
        letters = string.ascii_uppercase
        return "".join(self.r.choice(letters) for _ in range(3)) + holder + self.r.choice(letters) + self.digits(4) + self.r.choice(letters)

    def gstin(self) -> str:
        state = f"{self.r.randint(1, 37):02d}"
        body = state + self.pan(self.choice("CF")) + str(self.r.randint(1, 9)) + "Z"
        return body + gstin_check_char(body)

    def passport(self) -> str:
        return self.r.choice("ABCDEFGHJKLMNPRSTUVW") + self.digits(6, "123456789") + self.r.choice("123456789")

    def voter_id(self) -> str:
        return "".join(self.r.choice(string.ascii_uppercase) for _ in range(3)) + self.digits(7, "123456789")

    def driving_licence(self) -> str:
        state = self.choice(sorted(STATE_CODES - {"DD", "DN", "OR"}))
        return f"{state}{self.r.randint(1, 50):02d}{self.r.randint(1995, 2023)}{self.digits(7)}"

    def ifsc(self) -> str:
        return self.choice(BANKS) + "0" + self.digits(6)

    def bank_account(self) -> str:
        return self.digits(self.r.choice([11, 12, 14, 16]), "123456789")

    def card(self, spaced: bool = True) -> str:
        prefix = self.choice(["4", "51", "53", "55", "60", "65", "4"])
        base = prefix + self.digits(15 - len(prefix))
        v = base + luhn_check_digit(base)
        return " ".join(v[i:i + 4] for i in range(0, 16, 4)) if spaced else v

    def upi(self, name: str | None = None) -> str:
        first = (name or self.name()).split()[0].lower()
        return f"{first}{self.r.randint(1, 999)}@{self.choice(UPI)}"

    def place(self):
        return self.choice(CITIES)

    def pin(self, prefix: str | None = None) -> str:
        prefix = prefix or self.choice(CITIES)[2]
        return prefix + self.digits(3)

    def address(self, city: str | None = None) -> str:
        city = city or self.choice(CITIES)[0]
        return f"Flat {self.r.randint(1, 999)}, {self.choice(STREETS)}, {city}"

    def latlong(self, city: str) -> tuple[float, float]:
        lat, lon = CITY_COORDS.get(city, (20.59, 78.96))
        return round(lat + self.r.uniform(-0.12, 0.12), 5), round(lon + self.r.uniform(-0.12, 0.12), 5)

    def ip(self) -> str:
        return f"{self.r.choice([49, 103, 106, 117, 122, 157, 182, 203])}.{self.r.randint(0, 255)}.{self.r.randint(0, 255)}.{self.r.randint(1, 254)}"

    def dob(self, fmt: str = "%Y-%m-%d") -> str:
        d = date(1950, 1, 1) + timedelta(days=self.r.randint(0, 365 * 55))
        return d.strftime(fmt)

    def date_between(self, start_days_ago: int, end_days_ago: int = 0) -> str:
        d = date.today() - timedelta(days=self.r.randint(end_days_ago, start_days_ago))
        return d.isoformat()

    def timestamp(self, days_ago: int = 900) -> str:
        t = datetime.now() - timedelta(days=self.r.randint(0, days_ago), seconds=self.r.randint(0, 86400))
        return t.strftime("%Y-%m-%d %H:%M:%S")

    def code(self, prefix: str, n: int = 6) -> str:
        return f"{prefix}{self.digits(n)}"
