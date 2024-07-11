import argparse
import os
import subprocess
import time
from datetime import datetime
import json
import requests
from pprint import pprint
import copy

def fetch_args():
    parser = argparse.ArgumentParser(description='Stream handler')
    parser.add_argument('-n', '--name', required=False, help='Streamer name')
    return parser.parse_args()

def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def fetch_metadata(streamer_name, api_url):
    def extract_base_domain(url):
        return url.split('/')[2]

    full_api_url = f"https://{extract_base_domain(api_url)}/info/{streamer_name}"
    print(f"{current_time()} Trying to fetch stream metadata")
    response = requests.get(full_api_url)
    
    if response.status_code != 200:
        print(f"Error: Failed to fetch data from {full_api_url}")
        return None

    data = response.json()
    if data == "Too many requests, please try again later.":
        print(f"{current_time()} {data}")
        return None
    else:
        return data

def determine_source(stream_source, streamer_name):
    stream_source_url = ""
    if stream_source == "twitch":
        stream_source_url = f"twitch.tv/{streamer_name}"
    elif stream_source == "kick":
        stream_source_url = f"kick.com/{streamer_name}"
    elif stream_source == "youtube":
        stream_source_url = f"youtube.com/@{streamer_name}/live"
    else:
        print(f"{current_time()} Unknown stream source: {stream_source}")
        exit(1)
    print(f"{current_time()} Stream source: {stream_source_url}")
    return stream_source_url

def current_time():
    return datetime.now().strftime("%H:%M:%S")

def load_config(config_file):
    config = {}
    with open(config_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.strip().split("=", 1)
                value = value.split('#')[0].strip()
                if value.startswith('('):
                    value = value.split('(')[1]
                    value = value.split(')')[0]
                    # Load list values
                    value = value.split('"')[1::2]
                else:
                    value = value.split('"')
                    for i, v in enumerate(value):
                        if i % 2 == 1:
                            value[i] = v.strip()
                    value = "".join(value)
                config[key] = value
    return config

def replace_vars(c):
    for key, value in c.items():
        if type(value) != str:
            continue
        for k, v in c.items():
            if k == key:
                continue
            if type(v) != str:
                continue
            c[key] = c[key].replace(f"$(${k})", v)
        for k, v in c.items():
            if k == key:
                continue
            if type(v) != str:
                continue
            c[key] = c[key].replace(f"${k}", v)
        

def main():
    # Constants
    YT_SECRETS = 'client_secrets_autovod.json'
    YT_TOKEN = 'request_autovod.token'
    args = fetch_args()
    streamer_name = args.name
    print(args)

    if not streamer_name and not os.path.exists("/.dockerenv"):
        print(f"{current_time()} Missing required argument: -n STREAMER_NAME")
        exit(1)

    if not streamer_name:
        streamer_name = os.getenv('STREAMER_NAME')

    print(f"{current_time()} Selected streamer: {streamer_name}")
    config_file = f"{streamer_name}.config"
    if not os.path.isfile(config_file):
        config_file = f"configs/{streamer_name}.config"

    if not os.path.isfile(config_file):
        print(f"{current_time()} Config file is missing")
        exit(1)

    orig_config = load_config(config_file)
    config = copy.deepcopy(orig_config)
    
    YT_SECRETS = "./secrets/" + YT_SECRETS
    YT_TOKEN = "./secrets/" + YT_TOKEN

    stream_source = config.get('STREAM_SOURCE')
    stream_source_url = determine_source(stream_source, streamer_name)

    video_duration = config.get('VIDEO_DURATION', '00:00:00')
    split_video_duration = config.get('SPLIT_VIDEO_DURATION')
    api_url = config.get('API_URL')

    while True:
        config = copy.deepcopy(orig_config)
        config['STREAMER_NAME'] = streamer_name
        config['TIME_DATE'] = datetime.now().strftime("%d-%m-%y")
        config['TIME_CLOCK'] = datetime.now().strftime("%H-%M-%S")
        replace_vars(config)
        pprint(config)
        
        variables = ["VIDEO_TITLE", "VIDEO_PLAYLIST", "VIDEO_DESCRIPTION", "RCLONE_FILENAME", "RCLONE_DIR", "LOCAL_FILENAME"]
        original_values = {var: config.get(var) for var in variables}

        if config.get('API_CALLS') == 'true':
            metadata = fetch_metadata(streamer_name, api_url)
            if metadata:
                fetched_title = metadata.get('stream_title')
                fetched_game = metadata.get('stream_game')
                if fetched_title != "null" and fetched_title != "initial_title":
                    for var in variables:
                        value = config.get(var)
                        if value:
                            value = value.replace("$STREAMER_TITLE", fetched_title).replace("$STREAMER_GAME", fetched_game)
                            config[var] = value

        if split_video_duration:
            video_duration = split_video_duration
            if datetime.now().strftime("%d-%m-%y") == config.get('TIME_DATE_CHECK'):
                current_part = int(config.get('CURRENT_PART', 1)) + 1
            else:
                current_part = 1
            config['CURRENT_PART'] = str(current_part)
            for var in ["VIDEO_TITLE", "RCLONE_FILENAME", "LOCAL_FILENAME"]:
                value = config.get(var)
                if value:
                    value = f"{value} Part_{current_part}"
                    config[var] = value

        streamlink_options = f"{config.get('STREAMLINK_QUALITY')} --hls-duration {video_duration} -O --loglevel {config.get('STREAMLINK_LOGS')}"
        streamlink_flags = " ".join(config.get('STREAMLINK_FLAGS'))
        re_encode = config.get('RE_ENCODE')
        
        upload_service = config.get('UPLOAD_SERVICE')
        if upload_service == "youtube":
            required_files = [YT_TOKEN, YT_SECRETS, config_file]
            if not all(os.path.isfile(file) for file in required_files):
                print(f"{current_time()} One or more required files are missing")
                exit(1)

            input_data = {
                "title": config.get('VIDEO_TITLE'),
                "privacyStatus": config.get('VIDEO_VISIBILITY'),
                "description": config.get('VIDEO_DESCRIPTION'),
                "playlistTitles": [config.get('VIDEO_PLAYLIST')]
            }
            input_file = f"/tmp/input.{streamer_name}"
            with open(input_file, 'w') as f:
                json.dump(input_data, f)

            command = f"streamlink {stream_source_url} {streamlink_options} {streamlink_flags} | youtubeuploader -secrets {YT_SECRETS} -cache {YT_TOKEN} -metaJSON {input_file} -filename -"
            if subprocess.run(command, shell=True).returncode != 0:
                print(f"{current_time()} youtubeuploader failed uploading the stream")
            else:
                config['TIME_DATE_CHECK'] = datetime.now().strftime("%d-%m-%y")
                print(f"{current_time()} Stream uploaded to youtube")

        elif upload_service == "rclone":
            temp_file = run_command('mktemp stream.XXXXXX')
            if re_encode == "true":
                command = f"streamlink {stream_source_url} {streamlink_options} {streamlink_flags}--stdout | ffmpeg -i pipe:0 -c:v {config.get('RE_ENCODE_CODEC')} -crf {config.get('RE_ENCODE_CRF')} -preset {config.get('RE_ECODE_PRESET')} -hide_banner -loglevel {config.get('RE_ENCODE_LOG')} -f matroska {temp_file}"
            else:
                command = f"streamlink {stream_source_url} {streamlink_options} {streamlink_flags} -o - > {temp_file}"
            if subprocess.run(command, shell=True).returncode != 0:
                print(f"{current_time()} streamlink or ffmpeg failed")
            else:
                print(f"{current_time()} Stream saved to disk as {temp_file}")

            rclone_remote = config.get('RCLONE_REMOTE')
            rclone_dir = config.get('RCLONE_DIR')
            rclone_filename = config.get('RCLONE_FILENAME')
            rclone_fileext = config.get('RCLONE_FILEEXT')

            command = f"rclone copyto {temp_file} {rclone_remote}:{rclone_dir}/{rclone_filename}.{rclone_fileext}"
            if subprocess.run(command, shell=True).returncode != 0:
                print(f"{current_time()} rclone failed uploading the stream")
                if config.get('SAVE_ON_FAIL') == "true":
                    failed_temp_file = run_command(f'mktemp stream_failed_{streamer_name}.XXXXXX')
                    os.rename(temp_file, failed_temp_file)
                    print(f"{current_time()} Temp file renamed to {failed_temp_file}")
            else:
                print(f"{current_time()} Stream uploaded to rclone")
                os.remove(temp_file)
                config['TIME_DATE_CHECK'] = datetime.now().strftime("%d-%m-%y")

        elif upload_service == "restream":
            rtmps_url = config.get('RTMPS_URL')
            rtmps_stream_key = config.get('RTMPS_STREAM_KEY')
            command = f"streamlink {stream_source_url} {streamlink_options} {streamlink_flags} -O | ffmpeg -re -i - -ar {config.get('AUDIO_BITRATE')} -acodec {config.get('AUDIO_CODEC')} -vcodec copy -f {config.get('FILE_FORMAT')} {rtmps_url}{rtmps_stream_key}"
            if subprocess.run(command, shell=True).returncode != 0:
                print(f"{current_time()} ffmpeg failed re-streaming the stream")
            else:
                print(f"{current_time()} Stream re-streamed to {config.get('RTMPS_CHANNEL')}")
                config['TIME_DATE_CHECK'] = datetime.now().strftime("%d-%m-%y")

        elif upload_service == "local":
            local_filename = config.get('LOCAL_FILENAME')
            local_extension = config.get('LOCAL_EXTENSION')
            if re_encode == "true":
                command = f"streamlink {stream_source_url} {streamlink_options} {streamlink_flags} --stdout | ffmpeg -i pipe:0 -c:v {config.get('RE_ENCODE_CODEC')} -crf {config.get('RE_ENCODE_CRF')} -preset {config.get('RE_ECODE_PRESET')} -hide_banner -loglevel {config.get('RE_ENCODE_LOG')} -f matroska {local_filename}"
            else:
                command = f"streamlink {stream_source_url} {streamlink_options} {streamlink_flags} -o - > '{local_filename}.{local_extension}'"
            print(command)
            if subprocess.run(command, shell=True).returncode != 0:
                print(f"{current_time()} streamlink or ffmpeg failed saving the stream to disk")
                if config.get('SAVE_ON_FAIL') == "true":
                    failed_local_filename = f"{local_filename}_failed.{local_extension}"
                    os.rename(f"{local_filename}.{local_extension}", failed_local_filename)
                    print(f"{current_time()} Local failed file renamed to {failed_local_filename}")
            else:
                print(f"{current_time()} Stream saved to disk as {local_filename}.{local_extension}")
                config['TIME_DATE_CHECK'] = datetime.now().strftime("%d-%m-%y")

        else:
            print(f"{current_time()} Invalid upload service specified: {upload_service}")
            exit(1)

        for var in variables:
            config[var] = original_values[var]

        print(f"{current_time()} Trying again in 1 minute")
        time.sleep(60)

if __name__ == "__main__":
    main()
