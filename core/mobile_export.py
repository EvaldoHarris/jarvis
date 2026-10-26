"""Explicit authenticated exports for the native phone settings UI; never LLM tools."""
from memory.config_manager import get_plugin_config


def home_config():
    from plugins.cameras_locais import _cameras
    cameras = []
    for index, camera in enumerate(_cameras()):
        item = {key: camera.get(key, '') for key in (
            'name', 'host', 'vendor', 'username', 'password', 'port', 'channel', 'stream')}
        count = str(camera.get('channel_count') or '').strip()
        item['channel_count'] = int(count) if count.isdigit() and 1 <= int(count) <= 64 else 64
        item['id'] = f'pc-camera-{index + 1}'
        cameras.append(item)
    config = get_plugin_config('luzes_tuya')
    return {'version': 1, 'cameras': cameras, 'tuya': {
        key: str(config.get(key) or '') for key in ('api_key', 'api_secret', 'region')}}


def memories():
    from memory.memory_manager import all_entries_for_ui
    return {'memories': [
        {'key': str(item.get('category') or 'notes') + ': ' + str(item.get('key') or ''),
         'value': str(item.get('value') or '')}
        for item in all_entries_for_ui()[:200]
    ]}
