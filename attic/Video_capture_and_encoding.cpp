#include <fcntl.h>
#include <linux/videodev2.h>
#include "rk_mpi.h"
 
bool initCamera(const char* dev = "/dev/video52") {
    int fd = open(dev, O_RDWR);
    if (fd < 0) return false;
    
    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = 1280;
    fmt.fmt.pix.height = 720;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUV420;
    
    if (ioctl(fd, VIDIOC_S_FMT, &fmt) != 0) {
        close(fd);
        return false;
    }
    
    return true;
}
 
bool initEncoder() {
    MPP_RET ret = RK_MPI_SYS_Init();
    if (ret != MPP_OK) return false;
    
    MppCtx ctx;
    ret = mpp_create(&ctx, &mpi);
    if (ret != MPP_OK) return false;
    
    MppEncCfg cfg;
    mpp_enc_cfg_init(&cfg);
    
    // 设置编码参数
    mpp_enc_cfg_set_s32(cfg, "rc:mode", MPP_ENC_RC_MODE_CBR);
    mpp_enc_cfg_set_s32(cfg, "rc:bps_target", 1024*1024); // 1Mbps
    mpp_enc_cfg_set_s32(cfg, "rc:fps_in_num", 25);
    mpp_enc_cfg_set_s32(cfg, "rc:fps_in_denorm", 1);
    
    ret = mpi->control(ctx, MPP_ENC_SET_CFG, cfg);
    if (ret != MPP_OK) {
        mpp_destroy(ctx);
        return false;
    }
    
    encoder = ctx;
    return true;
}