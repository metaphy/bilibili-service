#!/usr/bin/env python3
import os
import requests
import sys
from string import Template
import subprocess

headers = {
    'Referer': 'https://www.bilibili.com',  
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'
}

template = "ffmpeg -i public/%s.mp4 -i public/%s.mp3 -c copy public/%s_new.mp4"
def saveFile(data, name):
    with open("./public/" + name, mode="wb") as f:
        f.write(data)

def generateFFMPEG(bvid):
    cmd = template % (bvid,bvid,bvid)
    print(cmd)
    return cmd

# 获取视频和音频的二进制流数据
def getMediaData(url, bvid):
    if not os.path.exists('./public'):
        os.makedirs('./public')

    if os.path.exists(f'./public/{bvid}_new.mp4'):
        return 

    videoResponse = requests.get(url.get("video"), headers=headers).content
    audioResponse = requests.get(url.get("audio"), headers=headers).content
    saveFile(videoResponse,bvid + ".mp4")
    saveFile(audioResponse,bvid + ".mp3")

    subprocess.call(generateFFMPEG(bvid),shell=True)

    flag = True
    if flag:
        try:
            os.remove('./public/' + bvid + '.mp4')
            print('删除成功')
        except:
            print('未删除！')
 
def main():
    videoUrl = sys.argv[1]
    audioUrl = sys.argv[2]
    bvid = sys.argv[3]

    # with open("./spider-params.txt", "r") as f:
    #     data = f.read()
    
    # params = data.split("\n")
    # videoUrl = params[0]
    # audioUrl = params[1]
    # bvid = params[2]

    getMediaData({
        "video": videoUrl,
        "audio": audioUrl
    },bvid)

    print("Succeeded!!!")
    
    # sys模块情况输出缓冲区
    sys.stdout.flush()

if __name__ == '__main__':
    main()