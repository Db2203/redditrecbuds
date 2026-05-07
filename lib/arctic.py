import time
import requests

BASE_URL = "https://arctic-shift.photon-reddit.com"
USER_AGENT = "audiorec/0.1 (https://github.com/Db2203/audiorec)"


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def get_json(session, path, params, max_retries=5):
    url = BASE_URL + path
    last = None
    for attempt in range(max_retries):
        r = session.get(url, params=params, timeout=60)
        last = r
        if r.status_code == 200:
            return r.json()
        # 422 here = arctic shift's backend query timeout, not a client error.
        # back off harder than you'd think — their db gets unhappy under load.
        if r.status_code in (422, 429, 500, 502, 503, 504):
            time.sleep(3 + 3 * attempt)
            continue
        r.raise_for_status()
    last.raise_for_status()


def paginate(session, path, params, batch_size=50, sleep_s=1.0, oldest_utc=None):
    """Walk backward through results.

    arctic shift has no cursor. sort=asc + a wide time range causes their
    backend to timeout (422), so we leave sort default (desc) and step
    backward by setting `before` to the min created_utc of the last batch.
    """
    params = dict(params)
    params["limit"] = batch_size

    last_min = None
    while True:
        data = get_json(session, path, params)
        items = data.get("data", []) if isinstance(data, dict) else data
        if not items:
            break

        for item in items:
            yield item

        if len(items) < batch_size:
            break

        new_min = min(it.get("created_utc", 0) for it in items if it.get("created_utc"))
        if not new_min or (last_min is not None and new_min >= last_min):
            break  # safety: timestamps not advancing
        if oldest_utc is not None and new_min <= oldest_utc:
            break
        last_min = new_min
        params["before"] = new_min
        time.sleep(sleep_s)
