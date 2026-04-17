import os
from dataclasses import dataclass
from typing import Optional
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

@dataclass
class Config:
    telegram_token: Optional[str]; openai_api_key: Optional[str]; google_sheet_id: Optional[str]
    google_credentials_path: Optional[str]; sheet_range: str; cache_ttl_seconds: int
    openai_model: str; mock_mode: bool

    @classmethod
    def load(cls):
        tok=os.getenv('TELEGRAM_TOKEN'); oai=os.getenv('OPENAI_API_KEY'); gid=os.getenv('GOOGLE_SHEET_ID')
        mock=os.getenv('MOCK_MODE','').lower() in ('1','true','yes') or not (tok and oai and gid)
        return cls(tok,oai,gid,os.getenv('GOOGLE_CREDENTIALS_PATH','credentials.json'),
            os.getenv('SHEET_RANGE','Sheet1!A1:Z1000'),int(os.getenv('CACHE_TTL_SECONDS','60')),
            os.getenv('OPENAI_MODEL','gpt-4o-mini'),mock)
