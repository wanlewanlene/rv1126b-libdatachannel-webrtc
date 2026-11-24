/* ============================================================================
 * 电机控制面板共享逻辑（Browser_client.html / Dual_webrtc.html 共用）
 *
 * 依赖页面元素：#aCtl #bCtl #motorStatus（面板标记仍写在各自页面里）
 * 接口：<origin>/motor/api/...（3000 端口同源反代到 8081）
 *
 * 暴露：mcmd(motor, op) / mrestart() / mrefresh()
 * ==========================================================================*/
(function () {
    'use strict';

    var MAPI = location.origin + '/motor';

    function statusEl() {
        return document.getElementById('motorStatus');
    }

    function refresh() {
        fetch(MAPI + '/api/status').then(function (r) {
            return r.json();
        }).then(function (j) {
            var el = statusEl();
            if (!el || !j || !j.A || !j.B) { return; }
            el.textContent =
                'A[' + j.A.mode + ']duty=' + j.A.duty +
                ' rpm=' + (j.A.last_rpm || 0).toFixed(0) + ' cnt=' + j.A.total +
                '  B[' + j.B.mode + ']duty=' + j.B.duty +
                ' rpm=' + (j.B.last_rpm || 0).toFixed(0) + ' cnt=' + j.B.total;
            el.style.color = '#3fb950';
        }).catch(function () {
            var el = statusEl();
            if (el) {
                el.textContent = '电机网桥不可达(:8081)';
                el.style.color = '#f85149';
            }
        });
    }

    window.mcmd = function (m, op) {
        var el = document.getElementById(m.toLowerCase() + 'Ctl');
        var v = el ? el.value : '';
        fetch(MAPI + '/api/cmd?m=' + m + '&op=' + op + '&v=' + encodeURIComponent(v))
            .then(function (r) { return r.json(); })
            .then(refresh)
            .catch(function () {});
    };

    window.mrestart = function () {
        fetch(MAPI + '/api/push_restart').then(function () {
            setTimeout(refresh, 1500);
        }).catch(function () {});
    };

    window.mrefresh = refresh;
    setInterval(refresh, 1000);
    refresh();
})();
