/**
 * Service Worker for 瑜伽馆管理系统 PWA
 * 提供离线缓存支持
 */

const CACHE_NAME = 'yoga-studio-v1.0.0';
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/manifest.json',
  '/members',
  '/classes',
  '/finance',
  '/booking'
];

// 安装事件：缓存静态资源
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        console.log('[SW] 缓存静态资源');
        return cache.addAll(urlsToCache);
      })
      .then(function() {
        console.log('[SW] 安装完成');
        return self.skipWaiting();
      })
  );
});

// 激活事件：清理旧缓存
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] 删除旧缓存:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(function() {
      console.log('[SW] 激活完成');
      return self.clients.claim();
    })
  );
});

// 拦截请求：优先使用缓存，失败则网络请求
self.addEventListener('fetch', function(event) {
  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        // 缓存命中，返回缓存
        if (response) {
          console.log('[SW] 缓存命中:', event.request.url);
          return response;
        }

        // 缓存未命中，发起网络请求
        console.log('[SW] 网络请求:', event.request.url);
        return fetch(event.request).then(function(response) {
          // 检查返回是否正常
          if (!response || response.status !== 200 || response.type !== 'basic') {
            return response;
          }

          // 克隆响应（响应流只能读一次）
          var responseToCache = response.clone();

          caches.open(CACHE_NAME)
            .then(function(cache) {
              console.log('[SW] 缓存新资源:', event.request.url);
              cache.put(event.request, responseToCache);
            });

          return response;
        });
      })
      .catch(function() {
        console.log('[SW] 离线且缓存未命中:', event.request.url);
        // 可以返回一个离线页面
      })
  );
});
