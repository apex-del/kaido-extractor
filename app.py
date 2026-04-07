"""
Kaido.to / RapidCloud Anime Extractor API for Vercel (Flask)
Extracts M3U8 from anime streaming sites
"""

import json
import re
import os
from flask import Flask, request, jsonify
import urllib.request

app = Flask(__name__)

BASE_URL = "https://kaido.to"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}


def get(url, headers=None, params=None):
    if params:
        url += '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except:
        return None


def get_episode_id(slug, episode=1):
    """Get episode ID from anime slug and episode number"""
    match = re.search(r'-(\d+)$', slug)
    if not match:
        return None
    anime_id = match.group(1)
    html = get(f"{BASE_URL}/ajax/episode/list/{anime_id}", HEADERS)
    if not html:
        return None
    try:
        data = json.loads(html)
        matches = re.findall(r'\?ep=(\d+)', data.get('html', '') if isinstance(data, dict) else data)
        if matches:
            episode_idx = int(episode) - 1
            if episode_idx < len(matches):
                return matches[episode_idx]
            return matches[0]
    except:
        pass
    return None


def get_source(server_id):
    """Get embed URL from server ID"""
    referer = {"Referer": f"{BASE_URL}/"}
    html = get(f"{BASE_URL}/ajax/episode/sources", {**HEADERS, **referer}, {"id": server_id})
    if not html:
        return None
    try:
        data = json.loads(html)
        return data.get("link")
    except:
        return None


def extract_rapidcloud(embed_url):
    """Extract M3U8 from RapidCloud embed URL"""
    source_match = re.search(r'embed-2/v2/e-1/([a-zA-Z0-9]+)', embed_url)
    if not source_match:
        return None, []
    
    source_id = source_match.group(1)
    api_url = f"https://rapid-cloud.co/embed-2/v2/e-1/getSources?id={source_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Referer": embed_url,
    }
    
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            sources = data.get("sources", [])
            if sources:
                m3u8 = sources[0].get("file") if isinstance(sources[0], dict) else sources[0]
                tracks = data.get("tracks", [])
                return m3u8, tracks
    except:
        pass
    return None, []


def extract(slug, episode=1, type="sub"):
    """Extract M3U8 from kaido.to"""
    episode_id = get_episode_id(slug, episode)
    if not episode_id:
        return {"success": False, "error": "Episode not found"}
    
    servers_url = f"{BASE_URL}/ajax/episode/servers?episodeId={episode_id}"
    referer = {"Referer": f"{BASE_URL}/"}
    html = get(servers_url, {**HEADERS, **referer})
    
    if not html:
        return {"success": False, "error": "Failed to get servers"}
    
    try:
        data = json.loads(html)
        html_content = data.get("html", "")
        items = re.findall(
            r'<div[^>]*data-type="(sub|dub)"[^>]*data-id="(\d+)"[^>]*data-server-id="(\d+)"[^>]*>.*?<a[^>]*class="btn"[^>]*>([^<]+)</a>',
            html_content, re.DOTALL
        )
        
        type_filtered = [(t, sid, ssid, sname) for t, sid, ssid, sname in items if t == type]
        if type_filtered:
            items = type_filtered
        
    except:
        return {"success": False, "error": "Failed to parse servers"}
    
    embed_url = None
    used_server = None
    
    for server_type, server_id, server_id_num, server_name in items:
        source = get_source(server_id)
        if source:
            embed_url = source
            used_server = {"name": server_name, "type": server_type, "id": server_id}
            break
    
    if not embed_url:
        return {"success": False, "error": f"No {type} embed URL found"}
    
    m3u8_url, tracks = extract_rapidcloud(embed_url)
    
    if not m3u8_url:
        return {"success": False, "error": "Failed to extract M3U8 from rapidcloud"}
    
    return {
        "success": True,
        "slug": slug,
        "episode": int(episode),
        "type": type,
        "m3u8_url": m3u8_url,
        "embed_url": embed_url,
        "server": used_server,
        "tracks": tracks,
    }


@app.route('/')
def home():
    return jsonify({
        "name": "Kaido/RapidCloud Anime Extractor API",
        "usage": "/api/extract?slug=anime-slug&episode=1&type=sub",
        "examples": [
            "/api/extract?slug=one-piece-100&episode=1&type=sub",
            "/api/extract?slug=monster-19&episode=1&type=sub"
        ]
    })


@app.route('/api/extract')
def api_extract():
    slug = request.args.get('slug', '')
    episode = request.args.get('episode', 1)
    type_param = request.args.get('type', 'sub').lower()
    
    if type_param not in ["sub", "dub"]:
        return jsonify({"success": False, "error": "Type must be 'sub' or 'dub'"}), 400
    
    if not slug:
        return jsonify({"success": False, "error": "Missing slug parameter"}), 400
    
    result = extract(slug, episode, type_param)
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True)
