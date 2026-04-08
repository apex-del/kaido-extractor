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


def extract_rapidcloud(embed_url, get_all_qualities=False):
    """Extract M3U8 from RapidCloud embed URL
    
    Args:
        embed_url: RapidCloud embed URL
        get_all_qualities: If True, return all quality variants info
    
    Returns:
        Tuple of (m3u8_url, tracks, qualities) where qualities is list of quality dicts
    """
    source_match = re.search(r'embed-2/v2/e-1/([a-zA-Z0-9]+)', embed_url)
    if not source_match:
        return None, [], []
    
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
            tracks = data.get("tracks", [])
            
            if sources:
                m3u8 = sources[0].get("file") if isinstance(sources[0], dict) else sources[0]
                
                # Return basic info
                if not get_all_qualities:
                    return m3u8, tracks, []
                
                # Return qualities info - note: actual quality parsing requires fetching master m3u8
                # which is blocked by CDN without browser-like headers
                qualities = [
                    {"quality": "master", "m3u8_url": m3u8, "note": "Use with Referer: https://rapid-cloud.co/"}
                ]
                return m3u8, tracks, qualities
    except:
        pass
    return None, [], []


def extract(slug, episode=1, type="sub", get_all_qualities=False):
    """Extract M3U8 from kaido.to
    
    Args:
        slug: Anime slug (e.g., 'one-piece-100')
        episode: Episode number
        type: 'sub' or 'dub'
        get_all_qualities: If True, include quality variants info
    
    Returns:
        Dict with success status and stream info
    """
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
    
    m3u8_url, tracks, qualities = extract_rapidcloud(embed_url, get_all_qualities)
    
    if not m3u8_url:
        return {"success": False, "error": "Failed to extract M3U8 from rapidcloud"}
    
    result = {
        "success": True,
        "slug": slug,
        "episode": int(episode),
        "type": type,
        "m3u8_url": m3u8_url,
        "embed_url": embed_url,
        "server": used_server,
        "tracks": tracks,
    }
    
    if get_all_qualities:
        result["qualities"] = qualities
        result["fetch_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://rapid-cloud.co/",
        }
    
    return result


@app.route('/')
def home():
    return jsonify({
        "name": "Kaido/RapidCloud Anime Extractor API",
        "version": "2.0",
        "usage": "/api/extract?slug=anime-slug&episode=1&type=sub",
        "features": {
            "extract": "Get stream URL for anime episode",
            "sources": "Get sources directly from embed URL"
        },
        "examples": [
            "/api/extract?slug=one-piece-100&episode=1&type=sub",
            "/api/extract?slug=monster-19&episode=1&type=sub&qualities=true",
            "/api/sources?url=https://rapid-cloud.co/embed-2/v2/e-1/VIDEO_ID"
        ],
        "note": "For CDN access, use headers: Referer: https://rapid-cloud.co/"
    })


@app.route('/api/extract')
def api_extract():
    slug = request.args.get('slug', '')
    episode = request.args.get('episode', 1)
    type_param = request.args.get('type', 'sub').lower()
    get_all_qualities = request.args.get('qualities', 'false').lower() == 'true'
    
    if type_param not in ["sub", "dub"]:
        return jsonify({"success": False, "error": "Type must be 'sub' or 'dub'"}), 400
    
    if not slug:
        return jsonify({"success": False, "error": "Missing slug parameter"}), 400
    
    result = extract(slug, episode, type_param, get_all_qualities)
    return jsonify(result)


@app.route('/api/sources')
def api_sources():
    """Direct endpoint to get sources from embed URL (for testing)"""
    embed_url = request.args.get('url', '')
    
    if not embed_url:
        return jsonify({"success": False, "error": "Missing url parameter"}), 400
    
    if 'rapid-cloud.co' not in embed_url:
        return jsonify({"success": False, "error": "Only rapid-cloud.co URLs supported"}), 400
    
    m3u8_url, tracks, qualities = extract_rapidcloud(embed_url, get_all_qualities=True)
    
    if not m3u8_url:
        return jsonify({"success": False, "error": "Failed to extract from rapidcloud"})
    
    return jsonify({
        "success": True,
        "m3u8_url": m3u8_url,
        "tracks": tracks,
        "qualities": qualities,
        "fetch_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://rapid-cloud.co/",
        }
    })


if __name__ == '__main__':
    app.run(debug=True)
