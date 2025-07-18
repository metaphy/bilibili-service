const { spawn } = require('child_process');
module.exports = function parseDash(obj,bvid) {
   
    return new Promise((res,rej) => {
        let videoUrl = obj.video[0].base_url;
        let audioUrl = obj.audio[0].base_url;
        let py = spawn("python3", ['./spider.py', videoUrl, audioUrl, bvid])

        py.stdout.on("data", (path) => {
            res(path);
            console.log("视频保存成功!!!")
        })
    })

}


// http://127.0.0.1:8000/getVideoData?bvid=BV1xz421B7ku

