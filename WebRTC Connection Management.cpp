#include <rtc/rtc.hpp>
 
std::shared_ptr<rtc::PeerConnection> createPeerConnection() {
    rtc::Configuration config;
    config.iceServers.emplace_back("stun:stun.l.google.com:19302");
    
    auto pc = std::make_shared<rtc::PeerConnection>(config);
    
    pc->onLocalDescription([](rtc::Description description) {
        // 发送SDP到信令服务器
        sendToSignalingServer(description.sdp());
    });
    
    pc->onLocalCandidate([](rtc::Candidate candidate) {
        // 发送ICE candidate
        sendCandidateToServer(candidate);
    });
    
    pc->onStateChange([](rtc::PeerConnection::State state) {
        if (state == rtc::PeerConnection::State::Connected) {
            // 连接建立成功
        }
    });
    
    return pc;
}