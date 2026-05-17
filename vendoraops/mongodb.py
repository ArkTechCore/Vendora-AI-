import logging
from functools import lru_cache

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


try:
    import certifi
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
except ImportError:  # pragma: no cover - handled at runtime in deployments
    certifi = None
    MongoClient = None
    PyMongoError = Exception
    ServerSelectionTimeoutError = Exception


AI_REPORTS = "aiReports"
INVESTIGATION_REPORTS = "investigationReports"


@lru_cache(maxsize=1)
def get_mongo_client():
    uri = getattr(settings, "MONGODB_URI", "")
    if not uri or MongoClient is None:
        return None
    return MongoClient(
        uri,
        tls=True,
        tlsCAFile=certifi.where() if certifi else None,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=15000,
        retryWrites=True,
    )


def get_mongo_database():
    client = get_mongo_client()
    if client is None:
        return None
    return client[getattr(settings, "MONGODB_DB", "vendora_ai")]


def get_collection(name):
    db = get_mongo_database()
    if db is None:
        return None
    return db[name]


def ping_mongodb():
    if not getattr(settings, "MONGODB_URI", ""):
        return False, "MONGODB_URI is not configured"
    if MongoClient is None:
        return False, "pymongo is not installed"
    try:
        client = get_mongo_client()
        if client is None:
            return False, "MongoDB client is unavailable"
        client.admin.command("ping")
        return True, "MongoDB connected successfully"
    except ServerSelectionTimeoutError as exc:
        return False, f"MongoDB connection timed out: {exc}"
    except PyMongoError as exc:
        return False, f"MongoDB connection failed: {exc}"


def log_mongodb_startup_status():
    ok, message = ping_mongodb()
    if ok:
        logger.info(message)
    else:
        logger.warning(message)
    return ok


def insert_document(collection_name, document):
    collection = get_collection(collection_name)
    if collection is None:
        logger.warning("MongoDB write skipped: collection %s unavailable", collection_name)
        return ""
    payload = {**document, "createdAt": document.get("createdAt") or timezone.now()}
    try:
        result = collection.insert_one(payload)
        logger.info("Saved document to MongoDB collection %s: %s", collection_name, result.inserted_id)
        return str(result.inserted_id)
    except PyMongoError as exc:
        logger.error("MongoDB write failed for collection %s: %s", collection_name, exc)
        return ""
