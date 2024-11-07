import datetime
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import click
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from flask import Flask, render_template, request
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from ratelimit import limits, sleep_and_retry

actual_int = int

INT_PER_K = 1000
INT_PER_M = INT_PER_K**2
INT_PER_B = INT_PER_K**3


def read_csv_pandas(csv_file):
    """Read a CSV file into a pandas DataFrame."""
    try:
        df = pd.read_csv(csv_file).replace(np.nan, None).replace("--", None)
        return df
    except Exception as e:
        logger.exception(f"Error reading CSV file: {e}")
        return None


def convert_to_int(value):
    if value.endswith("K"):
        return actual_int(float(value[:-1]) * INT_PER_K)
    elif value.endswith("M"):
        return actual_int(float(value[:-1]) * INT_PER_M)
    elif value.endswith("B"):
        return actual_int(float(value[:-1]) * INT_PER_B)
    else:
        return actual_int(value)


def custom_int_to_str(value):
    value = int(value)
    if type(value) is not type(1):  # bcz, int is now custom method
        return value
    if value < INT_PER_K:
        value = str(value)
    elif value < INT_PER_M:
        value = f"{value/INT_PER_K}K"

    elif value < INT_PER_B:
        value = f"{value/INT_PER_M}M"
    else:
        value = f"{value/INT_PER_B}B"

    return value


def int(value):
    if value in ["None", None]:
        return None

    if type(value) is str:
        if any(c in value for c in ["M", "K", "B"]):
            return convert_to_int(value)
        return actual_int(value.replace(",", ""))
    else:
        return actual_int(value)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


class YouTubeAuth:
    """Handle YouTube API authentication."""

    def __init__(self, credentials_file: str = "credentials.json"):
        self.credentials_file = credentials_file
        self.token_file = "token.json"

    def get_credentials(self) -> Credentials:
        """Get or refresh YouTube API credentials."""
        creds = None
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            except Exception as e:
                logger.exception(f"Error loading token file: {e}")
                os.remove(self.token_file)
                logger.info("Removed invalid token file")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._save_token(creds)
                except Exception as e:
                    logger.exception(f"Error refreshing token: {e}")
                    creds = None

            if not creds:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Credentials file not found at {self.credentials_file}. "
                        "Please download it from Google Cloud Console."
                    )
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    self._save_token(creds)
                except Exception as e:
                    raise Exception(f"Failed to authenticate: {e}")

        return creds

    def _save_token(self, creds: Credentials) -> None:
        """Save credentials to token file."""
        try:
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())
        except Exception as e:
            logger.exception(f"Error saving token: {e}")


@dataclass
class DailyStats:
    """Data structure for daily channel statistics."""

    date: str
    day: str
    subscriber_growth: str
    total_subscribers: str
    video_views: str
    total_views: str
    estimated_earnings: str


@dataclass
class AverageStats:
    """Data structure for average statistics."""

    name: str
    subscriber_growth: str
    view_growth: str
    estimated_earnings: str


@dataclass
class SocialBladeStats:
    """Enhanced data structure for Social Blade channel statistics."""

    avatar: str = "N/A"
    name: str = "N/A"
    username: str = "N/A"
    profile_url: str = "N/A"
    subscribers: str = "N/A"
    total_views: str = "N/A"
    uploads: str = "N/A"
    country: str = "N/A"
    channel_type: str = "N/A"
    created: str = "N/A"
    subscribers_last_30_days: str = "N/A"
    subscribers_growth_30_days: str = "N/A"
    estimated_monthly_earnings: str = "N/A"
    video_views_last_30_days: str = "N/A"
    video_views_growth_30_days: str = "N/A"
    recent_daily_stats_json: List[DailyStats] = None
    daily_average_stats_json: AverageStats = None
    weekly_average_stats_json: AverageStats = None
    monthly_average_stats_json: AverageStats = None

    last_video_upload_date: str = "N/A"
    last_50_videos_stats_json: List[Dict] = None


class SocialBladeScraper:
    """Enhanced Social Blade data scraper using specific query selectors."""

    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()

    @sleep_and_retry
    @limits(calls=2, period=10)  # 2 requests per 10 seconds
    def fetch_channel_stats(self, channel_id: str) -> Optional[SocialBladeStats]:
        """Fetch channel statistics from Social Blade using specific query selectors."""
        try:
            headers = {
                "User-Agent": self.ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            url = f"https://socialblade.com/youtube/channel/{channel_id}"
            response = self.session.get(url, headers=headers, timeout=60)

            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch Social Blade data for {channel_id}: {response.status_code}"
                )
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            stats = SocialBladeStats(
                avatar=self._get_text(soup, "#YouTubeUserTopInfoAvatar", attr="src"),
                name=self._get_text(soup, "#YouTubeUserTopInfoBlockTop h1"),
                username=self._get_text(soup, "#YouTubeUserTopInfoBlockTop h4 a"),
                profile_url=self._get_text(
                    soup, "#YouTubeUserTopInfoBlockTop h4 a", attr="href"
                ),
                subscribers=self._get_text(
                    soup,
                    "#YouTubeUserTopInfoBlock div.YouTubeUserTopInfo:nth-child(3) > span:nth-child(3)",
                ),
                total_views=self._get_text(
                    soup,
                    "#YouTubeUserTopInfoBlock div.YouTubeUserTopInfo:nth-child(4) > span:nth-child(3)",
                ),
                uploads=self._get_text(
                    soup,
                    "#YouTubeUserTopInfoBlock .YouTubeUserTopInfo:nth-child(2) span:nth-child(3)",
                ),
                country=self._get_text(soup, "#youtube-user-page-country"),
                channel_type=self._get_text(soup, "#youtube-user-page-channeltype"),
                created=self._get_text(
                    soup,
                    "#YouTubeUserTopInfoBlock .YouTubeUserTopInfo:nth-child(7) span:nth-child(3)",
                ),
                subscribers_last_30_days=self._get_text(
                    soup,
                    "#socialblade-user-content > div:nth-child(3) > div:nth-child(1) > p:nth-child(1)",
                    call_firstChild=True,
                ),
                subscribers_growth_30_days=self._get_text(
                    soup,
                    "#socialblade-user-content > div:nth-child(3) > div:nth-child(1) > p:nth-child(1) > sup:nth-child(1) > span:nth-child(1)",
                ),
                estimated_monthly_earnings=self._get_text(
                    soup,
                    "#socialblade-user-content > div:nth-child(3) > div:nth-child(2) > p:nth-child(1)",
                ),
                video_views_last_30_days=self._get_text(
                    soup,
                    "#socialblade-user-content > div:nth-child(3) > div:nth-child(3) > p:nth-child(1)",
                    call_firstChild=True,
                ),
                video_views_growth_30_days=self._get_text(
                    soup,
                    "#socialblade-user-content > div:nth-child(3) > div:nth-child(3) > p:nth-child(1) > sup:nth-child(1) > span:nth-child(1)",
                ),
            )

            # Fetch video stats
            video_result = self.fetch_video_stats(channel_id)
            if video_result:
                last_video_upload_date, last_50_videos_stats = video_result
                stats.last_video_upload_date = last_video_upload_date
                stats.last_50_videos_stats_json = json.dumps(last_50_videos_stats)

            # Get recent daily stats
            stats.recent_daily_stats_json = self._extract_recent_daily_stats(soup)

            # Get average stats
            stats.daily_average_stats_json = self._extract_daily_average(soup)
            stats.weekly_average_stats_json = self._extract_average(soup, "weekly")
            stats.monthly_average_stats_json = self._extract_average(soup, "monthly")

            return stats

        except Exception as e:
            logger.exception(f"Error scraping Social Blade for {channel_id}: {e}")
            return None

    def _get_text(
        self,
        soup: BeautifulSoup,
        selector: str,
        attr: Optional[str] = None,
        call_firstChild: bool = False,
    ) -> str:
        """Extract text or attribute from element using CSS selector."""
        try:
            element = soup.select_one(selector)
            if not element:
                return "N/A"
            if attr:
                return element.get(attr, "N/A")
            if call_firstChild:
                return element.contents[0].text.strip()
            return element.text.strip()
        except Exception:
            return "N/A"

    def _extract_recent_daily_stats(self, soup: BeautifulSoup) -> List[DailyStats]:
        """Extract recent daily statistics."""
        try:
            all_divs = soup.select("#socialblade-user-content > div")
            daily_stats = []

            # Get elements 7 to 20 (14 days of data)
            for element in all_divs[6:20]:
                daily_stat = DailyStats(
                    date=self._get_text(element, "div:nth-child(1)"),
                    day=self._get_text(element, "div:nth-child(2)"),
                    subscriber_growth=self._get_text(
                        element, "div:nth-child(3) div:nth-child(1) span"
                    )
                    or "--",
                    total_subscribers=self._get_text(
                        element, "div:nth-child(3) div:nth-child(2)"
                    ),
                    video_views=self._get_text(
                        element, "div:nth-child(4) div:nth-child(1) span"
                    ),
                    total_views=self._get_text(
                        element, "div:nth-child(4) div:nth-child(2)"
                    ),
                    estimated_earnings=self._get_text(element, "div:nth-child(5)"),
                )
                daily_stats.append(daily_stat)

            return daily_stats
        except Exception as e:
            logger.exception(f"Error extracting daily stats: {e}")
            return []

    def _extract_daily_average(self, soup: BeautifulSoup) -> AverageStats:
        """Extract daily average statistics."""
        try:
            daily_div = soup.select_one("#socialblade-user-content > div:nth-child(21)")
            return AverageStats(
                name=self._get_first_text(daily_div, "div:nth-child(1)"),
                subscriber_growth=self._get_text(daily_div, "#averagedailysubs span"),
                view_growth=self._get_text(daily_div, "#averagedailyviews span"),
                estimated_earnings=self._get_text(daily_div, "div:nth-child(4)"),
            )
        except Exception:
            return None

    def _extract_average(self, soup: BeautifulSoup, period: str) -> AverageStats:
        """Extract weekly or monthly average statistics."""
        try:
            selector = (
                "div:nth-child(22)" if period == "weekly" else "div:nth-child(23)"
            )
            avg_div = soup.select_one(f"#socialblade-user-content > {selector}")
            return AverageStats(
                name=self._get_first_text(avg_div, "div:nth-child(1)"),
                subscriber_growth=self._get_text(avg_div, "div:nth-child(2) span"),
                view_growth=self._get_text(avg_div, "div:nth-child(3) span"),
                estimated_earnings=self._get_text(avg_div, "div:nth-child(4) span"),
            )
        except Exception:
            return None

    def _get_first_text(self, element: BeautifulSoup, selector: str) -> str:
        """Get only the first text node from an element."""
        try:
            selected = element.select_one(selector)
            if not selected:
                return "N/A"
            return selected.find(string=True, recursive=False).strip()
        except Exception:
            return "N/A"

    @sleep_and_retry
    @limits(calls=2, period=10)  # 2 requests per 10 seconds
    def fetch_video_stats(self, channel_id: str) -> Optional[Tuple[str, List[Dict]]]:
        """Fetch the last 50 video statistics from Social Blade."""
        try:
            headers = {
                "User-Agent": self.ua.random,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://socialblade.com",
                "DNT": "1",
                "Connection": "keep-alive",
                "Referer": f"https://socialblade.com/youtube/channel/{channel_id}/videos",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-GPC": "1",
                "TE": "trailers",
            }

            data = {"channelid": channel_id}

            url = "https://socialblade.com/js/class/youtube-video-recent"
            response = self.session.post(url, headers=headers, data=data, timeout=60)

            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch video stats for {channel_id}: {response.status_code}"
                )
                return None

            video_stats = response.json()

            # Extract the last video upload date (assuming it's the first video's created_at date)
            last_video_upload_date = (
                video_stats[0]["created_at"] if video_stats else "N/A"
            )

            return last_video_upload_date, video_stats

        except Exception as e:
            logger.exception(f"Error scraping video stats for {channel_id}: {e}")
            return None


class YouTubeSubsFetcher:
    """Fetch and manage YouTube subscriptions."""

    def __init__(
        self, credentials: Optional[Credentials] = None, output_dir: str = "."
    ):
        if credentials:
            self.youtube = build("youtube", "v3", credentials=credentials)
        self.output_dir = output_dir
        self._ensure_output_dir()

        self.subs_file = os.path.join(output_dir, "subscriptions.csv")
        self.progress_file = os.path.join(output_dir, "fetch_progress.json")

    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        os.makedirs(self.output_dir, exist_ok=True)

    def _fetch_page(self, page_token: Optional[str] = None) -> Dict:
        """Fetch a single page of subscriptions."""
        request = self.youtube.subscriptions().list(
            part="snippet", mine=True, maxResults=50, pageToken=page_token
        )
        return request.execute()

    def fetch_subscriptions(self, resume: bool = True) -> None:
        """Fetch all YouTube subscriptions."""
        if resume and os.path.exists(self.subs_file):
            logger.info(f"Found existing subscription file: {self.subs_file}")
            return

        progress = {"next_page_token": None, "subscriptions": []}
        subscriptions = []

        try:
            while True:
                try:
                    response = self._fetch_page(progress["next_page_token"])
                    for item in response["items"]:
                        channel_data = {
                            "channel_id": item["snippet"]["resourceId"]["channelId"],
                            "channel_title": item["snippet"]["title"],
                            "social_blade_url": f"https://socialblade.com/youtube/channel/{item['snippet']['resourceId']['channelId']}",
                            "youtube_url": f"https://youtube.com/channel/{item['snippet']['resourceId']['channelId']}",
                            "fetch_date": datetime.datetime.now().isoformat(),
                        }
                        subscriptions.append(channel_data)

                    progress["next_page_token"] = response.get("nextPageToken")
                    logger.info(f"Fetched {len(subscriptions)} channels so far...")

                    if not progress["next_page_token"]:
                        break

                except Exception as e:
                    logger.exception(f"Error fetching page: {e}")
                    return

            # Save results
            df = pd.DataFrame(subscriptions)
            df.to_csv(self.subs_file, index=False)
            logger.info(f"\nFetch completed! Total subscriptions: {len(subscriptions)}")
            logger.info(f"Data saved to: {self.subs_file}")

        except Exception as e:
            logger.exception(f"Error during fetch: {e}")


class SocialBladeEnhancer:
    """Enhance subscription data with Social Blade statistics."""

    def __init__(self, input_file: str, output_dir: str = "."):
        self.input_file = input_file
        self.output_dir = output_dir
        self.enhanced_file = os.path.join(output_dir, "enhanced_subscriptions.csv")
        self.progress_file = os.path.join(output_dir, "socialblade_progress.json")
        self.scraper = SocialBladeScraper()

    def load_progress(self) -> Dict:
        """Load progress from previous enhancement."""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("Corrupt progress file found. Starting fresh.")
        return {"processed_channels": []}

    def save_progress(self, processed_channels: List[str]) -> None:
        """Save current progress."""
        with open(self.progress_file, "w") as f:
            json.dump({"processed_channels": processed_channels}, f)

    def enhance_data(self, resume: bool = True) -> None:
        """Enhance subscription data with Social Blade statistics."""
        try:
            # Load subscription data
            if not os.path.exists(self.input_file):
                raise FileNotFoundError(
                    f"Subscription file not found: {self.input_file}"
                )

            df = read_csv_pandas(self.input_file)
            logger.info(f"Loaded {len(df)} subscriptions from {self.input_file}")

            # Load progress if resuming
            progress = self.load_progress() if resume else {"processed_channels": []}
            processed_channels = set(progress["processed_channels"])

            try:
                # If enhanced file exists, load it to keep existing data
                if os.path.exists(self.enhanced_file):
                    enhanced_df = read_csv_pandas(self.enhanced_file)
                    df = pd.merge(
                        df,
                        enhanced_df.drop(
                            columns=[
                                "channel_title",
                                "youtube_url",
                                "social_blade_url",
                                "fetch_date",
                            ]
                        ),
                        on="channel_id",
                        how="left",
                    )

                for idx, row in df.iterrows():
                    if row["channel_id"] in processed_channels:
                        continue

                    logger.info(
                        f"Fetching Social Blade data for {row['channel_title']} ({idx + 1}/{len(df)})"
                    )
                    stats = self.scraper.fetch_channel_stats(row["channel_id"])

                    if stats:
                        # Handle complex objects separately
                        stats_dict = vars(stats).copy()

                        # Convert recent_daily_stats to JSON string if it exists
                        if stats_dict["recent_daily_stats_json"]:
                            stats_dict["recent_daily_stats_json"] = json.dumps(
                                [
                                    vars(stat)
                                    for stat in stats_dict["recent_daily_stats_json"]
                                ]
                            )

                        # Convert average stats to JSON strings if they exist
                        for avg_key in [
                            "daily_average",
                            "weekly_average",
                            "monthly_average",
                        ]:
                            if stats_dict[avg_key + "_stats_json"]:
                                stats_dict[avg_key + "_stats_json"] = json.dumps(
                                    vars(stats_dict[avg_key + "_stats_json"])
                                )

                        # Convert last 50 video stats to JSON string if it exists
                        if stats_dict["last_50_videos_stats_json"]:
                            stats_dict["last_50_videos_stats_json"] = stats_dict[
                                "last_50_videos_stats_json"
                            ]

                        # Update DataFrame with processed values
                        for key, value in stats_dict.items():
                            df.at[idx, f"socialblade_{key}"] = value

                    if (
                        stats is not None
                    ):  # Skip if no stats were found, maybe due to network issue? logged error in fetch method but no return
                        processed_channels.add(row["channel_id"])
                        self.save_progress(list(processed_channels))

                    # Save progress periodically
                    if idx % 10 == 0:
                        df.to_csv(self.enhanced_file, index=False)
                        logger.info(
                            f"Progress saved. Processed {idx + 1}/{len(df)} channels"
                        )

                # Final save
                df.to_csv(self.enhanced_file, index=False)

                if os.path.exists(self.progress_file):
                    os.remove(self.progress_file)

                logger.info("\nEnhancement completed!")
                logger.info(f"Enhanced data saved to: {self.enhanced_file}")

            except KeyboardInterrupt:
                logger.info("\nProcess interrupted by user. Saving progress...")
                df.to_csv(self.enhanced_file, index=False)
                self.save_progress(list(processed_channels))
                logger.info("Progress saved. You can resume later.")
                return

        except Exception as e:
            logger.exception(f"Error during enhancement: {e}")


@click.group()
def cli():
    """YouTube Subscription List Fetcher with Social Blade Analysis"""
    pass


@cli.command()
@click.option(
    "--credentials-file",
    default="credentials.json",
    help="Path to credentials.json file",
)
@click.option("--output-dir", default=".", help="Directory to save output files")
def fetch(credentials_file: str, output_dir: str):
    """Fetch YouTube subscription list."""
    try:
        logger.info("Starting subscription fetch process...")
        auth = YouTubeAuth(credentials_file)
        credentials = auth.get_credentials()
        fetcher = YouTubeSubsFetcher(credentials=credentials, output_dir=output_dir)
        fetcher.fetch_subscriptions()
    except Exception as e:
        logger.exception(f"Error: {e}")


@cli.command()
@click.option(
    "--input-file",
    default="subscriptions.csv",
    help="Input CSV file with subscription data",
)
@click.option("--output-dir", default=".", help="Directory to save output files")
@click.option(
    "--resume/--no-resume",
    default=True,
    help="Resume from last enhancement or start fresh",
)
def enhance(input_file: str, output_dir: str, resume: bool):
    """Enhance subscription data with Social Blade statistics."""
    try:
        logger.info("Starting Social Blade enhancement process...")
        enhancer = SocialBladeEnhancer(input_file=input_file, output_dir=output_dir)
        enhanced_file = os.path.join(output_dir, "enhanced_subscriptions.csv")

        if os.path.exists(enhanced_file):
            df = read_csv_pandas(enhanced_file)
            # Check if the last row has empty values, indicating ongoing enhancement
            last_row_last_value = df.iloc[-1].values[-1]
            if last_row_last_value is None:  # if last row last value is nan
                logger.info(
                    "Enhancement process is still ongoing. Resuming from the last state."
                )

            # if more than 5 means new colums were added and no nan values were found means it is done
            elif len(df.columns) > 5:
                logger.info("Enhancement process has already completed.")
                return
        enhancer.enhance_data(resume=resume)
    except Exception as e:
        logger.exception(f"Error: {e}")


@cli.command()
@click.option(
    "--input-file",
    default="enhanced_subscriptions.csv",
    help="Input CSV file with enhanced subscription data",
)
@click.option("--host", default="127.0.0.1", help="Host to run the local server on")
@click.option("--port", default=5000, help="Port to run the local server on")
def display(input_file: str, host: str, port: int):
    """Display enhanced subscription data as a web page."""
    try:
        app = Flask(__name__, template_folder="templates")

        # ---------------------
        @app.route("/", methods=["GET", "POST"])
        def index():
            try:
                # Load the CSV file
                df = read_csv_pandas(input_file)
                original_df = df.copy()  # Store the original DataFrame

                # Filter options from form
                # TODO: add option to list channel without last upload date, meaans have no videos uploaded
                before_upload_value = int(request.form.get("before_upload_value", 0))
                before_upload_unit = request.form.get("before_upload_unit", "days")
                after_upload_value = int(request.form.get("after_upload_value", 0))
                after_upload_unit = request.form.get("after_upload_unit", "days")
                sort_by = request.form.get("sort_by", "subscribers")
                sort_order = request.form.get("sort_order", "desc")
                filter_channel_types = request.form.get("filter_channel_types")

                # Function to convert time unit to days
                def get_days(value, unit):
                    if unit == "days":
                        return value
                    elif unit == "weeks":
                        return value * 7
                    elif unit == "months":
                        return value * 30
                    elif unit == "years":
                        return value * 365
                    else:
                        return 0

                # Filter based on upload date range (before and after)
                if before_upload_value > 0 and after_upload_value > 0:
                    before_upload_date = datetime.datetime.now() - datetime.timedelta(
                        days=get_days(before_upload_value, before_upload_unit)
                    )
                    after_upload_date = datetime.datetime.now() - datetime.timedelta(
                        days=get_days(after_upload_value, after_upload_unit)
                    )

                    # Convert `socialblade_last_video_upload_date` to datetime for comparison
                    df["socialblade_last_video_upload_date"] = pd.to_datetime(
                        df["socialblade_last_video_upload_date"], errors="coerce"
                    )

                    # Apply filter: last upload date between `after_upload_date` and `before_upload_date`
                    df = df[
                        (df["socialblade_last_video_upload_date"] <= before_upload_date)
                        & (
                            df["socialblade_last_video_upload_date"]
                            >= after_upload_date
                        )
                    ]

                # Filter by channel type
                if filter_channel_types:
                    if filter_channel_types == "None":
                        df = df[df["socialblade_channel_type"].isnull()]
                    else:
                        df = df[df["socialblade_channel_type"] == filter_channel_types]

                # Ensure correct sorting by converting columns to appropriate types
                if sort_by == "subscribers":
                    # use loop and change type to int but use custo int method to handle strings
                    df["socialblade_subscribers"] = df["socialblade_subscribers"].apply(
                        int
                    )
                    df = df.sort_values(
                        by="socialblade_subscribers", ascending=sort_order == "asc"
                    )
                elif sort_by == "views":
                    df["socialblade_total_views"] = df["socialblade_total_views"].apply(
                        int
                    )
                    df = df.sort_values(
                        by="socialblade_total_views", ascending=sort_order == "asc"
                    )
                elif sort_by == "upload_date":
                    df["socialblade_last_video_upload_date"] = pd.to_datetime(
                        df["socialblade_last_video_upload_date"], errors="coerce"
                    )
                    df = df.sort_values(
                        by="socialblade_last_video_upload_date",
                        ascending=sort_order == "asc",
                    )

                df = df.replace(
                    np.nan, None
                )  # Replace NaN with None, seems like None became NaN when turned str to int using custom method using apply
                # Prepare data for display
                data = []
                for _, row in df.iterrows():
                    channel_title = row["channel_title"]
                    channel_username = row["socialblade_username"]

                    channel_title = f"{channel_title}"
                    if channel_username:
                        channel_title += f" ({channel_username})"

                    subscriber_count = f"{int(row['socialblade_subscribers'])}"
                    total_views = f"{int(row['socialblade_total_views'])}"
                    youtuber_country = row["socialblade_country"]
                    if youtuber_country is None:
                        youtuber_country = ""
                    row_data = {
                        "channel_title": channel_title,
                        "youtube_url": row["youtube_url"],
                        "social_blade_url": row["social_blade_url"],
                        "socialblade_subscribers": subscriber_count,
                        "socialblade_total_views": total_views,
                        "socialblade_last_video_upload_date": row[
                            "socialblade_last_video_upload_date"
                        ],
                        "socialblade_country": youtuber_country,
                        "socialblade_channel_type": row["socialblade_channel_type"],
                        "socialblade_created": row["socialblade_created"],
                        "socialblade_subscribers_last_30_days": f"{row['socialblade_subscribers_last_30_days']}",
                        "socialblade_subscribers_growth_30_days": f"{row['socialblade_subscribers_growth_30_days']}%",
                        "socialblade_estimated_monthly_earnings": f"${row['socialblade_estimated_monthly_earnings']}",
                        "socialblade_video_views_last_30_days": f"{int(row['socialblade_video_views_last_30_days'])}",
                        "socialblade_video_views_growth_30_days": f"{row['socialblade_video_views_growth_30_days']}%",
                        "socialblade_avatar": row[
                            "socialblade_avatar"
                        ],  # Add avatar URL here
                    }
                    data.append(row_data)

                # Get unique channel types for the filter checkboxes
                unique_channel_types = original_df["socialblade_channel_type"].unique()
                unique_channel_types = [
                    channel_type or "None" for channel_type in unique_channel_types
                ]
                logger.info(f"Unique channel types: {unique_channel_types}")

                # Display count message
                total_results = len(df)
                total_actual_len = len(
                    original_df
                )  # Assuming you have the original unfiltered DataFrame stored as `original_df`
                count_message = (
                    f"Displaying {total_results} out of {total_actual_len} results."
                )

                return render_template(
                    "index.html",
                    data=data,
                    before_upload_value=before_upload_value,
                    before_upload_unit=before_upload_unit,
                    after_upload_value=after_upload_value,
                    after_upload_unit=after_upload_unit,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    filter_channel_types=filter_channel_types,
                    unique_channel_types=unique_channel_types,
                    count_message=count_message,
                    custom_int_to_str=custom_int_to_str,
                )
            except Exception as e:
                logger.exception(f"Error: {e}")
                return "An error occurred while processing your request."

        app.run(host=host, port=port, debug=True)
    except Exception as e:
        logger.exception(f"Error: {e}")


if __name__ == "__main__":
    cli()
