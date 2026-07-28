import random

from django.core.management.base import BaseCommand

from apps.market.services.market_service import MarketService


class Command(BaseCommand):

    help = "Import Demo Market Data"

    def handle(self, *args, **kwargs):

        companies = [

            ("RELIANCE","Reliance Industries"),

            ("TCS","Tata Consultancy Services"),

            ("INFY","Infosys"),

            ("HDFCBANK","HDFC Bank"),

            ("ICICIBANK","ICICI Bank"),

            ("SBIN","State Bank of India"),

            ("LT","Larsen & Toubro"),

            ("BHARTIARTL","Bharti Airtel"),

            ("ITC","ITC"),

            ("AXISBANK","Axis Bank"),

            ("KOTAKBANK","Kotak Mahindra Bank"),

            ("MARUTI","Maruti Suzuki"),

            ("BAJFINANCE","Bajaj Finance"),

            ("SUNPHARMA","Sun Pharma"),

            ("TITAN","Titan"),

            ("ADANIENT","Adani Enterprises"),

            ("POWERGRID","Power Grid"),

            ("ULTRACEMCO","UltraTech Cement"),

            ("NTPC","NTPC"),

            ("ONGC","ONGC"),

            ("COALINDIA","Coal India"),

            ("WIPRO","Wipro"),

            ("HCLTECH","HCL Technologies"),

            ("TECHM","Tech Mahindra"),

            ("INDUSINDBK","IndusInd Bank"),

            ("TATAMOTORS","Tata Motors"),

            ("M&M","Mahindra & Mahindra"),

            ("ASIANPAINT","Asian Paints"),

            ("NESTLEIND","Nestle India"),

            ("JSWSTEEL","JSW Steel"),

        ]

        total = 0

        for symbol, name in companies:

            ltp = round(random.uniform(100, 3500), 2)

            op = round(ltp - random.uniform(0, 40), 2)

            hp = round(max(ltp, op) + random.uniform(0, 25), 2)

            lp = round(min(ltp, op) - random.uniform(0, 25), 2)

            prev = round(op, 2)

            chg = round(ltp - prev, 2)

            chgp = round((chg / prev) * 100, 2)

            MarketService.save_quote(

                {

                    "symbol": symbol,

                    "company_name": name,

                    "last_price": ltp,

                    "open_price": op,

                    "high_price": hp,

                    "low_price": lp,

                    "previous_close": prev,

                    "change": chg,

                    "change_percent": chgp,

                    "volume": random.randint(

                        100000,

                        9000000,

                    ),

                    "traded_value": random.randint(

                        10000000,

                        900000000,

                    ),

                    "market_status": "OPEN",

                }

            )

            total += 1

        self.stdout.write(

            self.style.SUCCESS(

                f"{total} Stocks Imported Successfully."

            )

        )
