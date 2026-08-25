
#!/bin/bash
 
# 构建Docker镜像
docker build -t rv1106-webrtc-builder .
 
# 运行编译容器
docker run -it --rm \
    -v $(pwd):/app \
    rv1106-webrtc-builder \
    /bin/bash -c "cd /app && ./build.sh"