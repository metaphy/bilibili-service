import requests

def download_file(url, file_name):
    """Download a file from a URL to a local destination path."""
    response = requests.get(url, stream=True)
    response.raise_for_status()  # Raise an error for bad responses

    print(f"Downloading {file_name} from {url}...")
    print(f" - complete status code: {response.status_code}")
 

def start_download_batch():
    base_url = 'http://127.0.0.1:8000/getVideoData?bvid='
    file = 'download.csv'
    with open(file, 'r') as f:
        for line in f:
            bvid, file_name = line.strip().split(',')
            url = base_url + bvid
            print(url)
            download_file(url, file_name)

    print("All downloads completed.")

if __name__ == "__main__":
    start_download_batch()