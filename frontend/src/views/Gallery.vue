<template>
  <div class="gallery-page">
    <!-- 顶部工具栏 -->
    <div class="gallery-toolbar">
      <div class="toolbar-left">
        <!-- 筛选标签 -->
        <div class="filter-tabs">
          <button
            class="tab-btn"
            :class="{ active: activeFilter === 'all' }"
            @click="activeFilter = 'all'"
          >
            全部
            <span class="tab-count">{{ files.length }}</span>
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeFilter === 'image' }"
            @click="activeFilter = 'image'"
          >
            图片
            <span class="tab-count">{{ imageCount }}</span>
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeFilter === 'video' }"
            @click="activeFilter = 'video'"
          >
            视频
            <span class="tab-count">{{ videoCount }}</span>
          </button>
        </div>

        <span class="toolbar-stat">{{ formatSize(totalSize) }}</span>
      </div>

      <div class="toolbar-right">
        <div class="expire-box">
          <span class="expire-label">过期时间</span>
          <input
            type="number"
            v-model.number="expireHoursInput"
            :min="-1"
            :max="720"
            class="expire-input"
            @keyup.enter="handleSave"
          />
          <span class="expire-unit">小时</span>
          <HelpTip text="-1 表示永不自动删除，最小值为 1 小时。过期文件会自动删除！" />
          <button
            class="btn-save"
            @click="handleSave"
            :disabled="isSaving"
          >
            {{ isSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <div class="loading-spinner"></div>
      <p class="loading-text">加载中...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="filteredFiles.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" class="empty-icon" fill="currentColor">
        <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
      </svg>
      <p>暂无{{ activeFilter === 'video' ? '视频' : activeFilter === 'image' ? '图片' : '媒体' }}文件</p>
    </div>

    <!-- 瀑布流布局 -->
    <div v-else class="masonry-grid">
      <div
        v-for="file in filteredFiles"
        :key="file.filename"
        class="masonry-item"
        :class="{ 'is-expired': file.expired }"
      >
        <div class="media-wrapper" @click="openPreview(file)">
          <img
            v-if="file.type === 'image'"
            :src="getFileUrl(file.url)"
            :alt="file.filename"
            loading="lazy"
            class="media-content"
            @error="handleImageError($event)"
          />
          <div v-else class="video-placeholder">
            <svg viewBox="0 0 24 24" class="play-icon" fill="currentColor">
              <path d="M8 5v14l11-7z"/>
            </svg>
            <video
              :src="getFileUrl(file.url)"
              preload="metadata"
              muted
              class="media-content"
            ></video>
          </div>

          <div class="media-overlay">
            <button class="overlay-btn delete" @click.stop="handleDelete(file)" title="删除">
              <svg viewBox="0 0 24 24" fill="currentColor" class="btn-icon">
                <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
              </svg>
            </button>
            <button class="overlay-btn download" @click.stop="downloadFile(file)" title="下载">
              <svg viewBox="0 0 24 24" fill="currentColor" class="btn-icon">
                <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
              </svg>
            </button>
          </div>

          <div v-if="file.expired" class="expired-badge">已过期</div>
        </div>

        <div class="file-info">
          <p class="file-name" :title="file.filename">{{ file.filename }}</p>
          <div class="file-meta">
            <span class="file-size">{{ formatSize(file.size) }}</span>
            <Tooltip
              v-if="file.expires_in_seconds !== null && !file.expired"
              :text="'将在 ' + formatTimeRemaining(file.expires_in_seconds) + ' 后自动删除'"
            >
              <span class="file-countdown">{{ formatTimeRemaining(file.expires_in_seconds) }}</span>
            </Tooltip>
            <span class="file-type-badge" :class="file.type">
              {{ file.type === 'video' ? '视频' : '图片' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Lightbox 预览 -->
    <Teleport to="body">
      <div v-if="previewFile" class="lightbox" @click.self="closePreview">
        <div class="lightbox-content">
          <button class="lightbox-close" @click="closePreview">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
          <img
            v-if="previewFile.type === 'image'"
            :src="getFileUrl(previewFile.url)"
            :alt="previewFile.filename"
            class="lightbox-media"
          />
          <video
            v-else
            :src="getFileUrl(previewFile.url)"
            controls
            autoplay
            class="lightbox-media"
          ></video>
          <div class="lightbox-info">
            <span>{{ previewFile.filename }}</span>
            <span>{{ formatSize(previewFile.size) }}</span>
            <span>{{ previewFile.created_at }}</span>
            <button class="lightbox-dl-btn" @click="downloadFile(previewFile)">
              <svg viewBox="0 0 24 24" fill="currentColor" class="btn-icon-sm">
                <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
              </svg>
              下载
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 确认弹窗 -->
    <ConfirmDialog
      :open="confirmDialog.open.value"
      :title="confirmDialog.title.value"
      :message="confirmDialog.message.value"
      :confirm-text="confirmDialog.confirmText.value"
      :cancel-text="confirmDialog.cancelText.value"
      @confirm="confirmDialog.confirm"
      @cancel="confirmDialog.cancel"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { galleryApi, type GalleryFile } from '@/api/gallery'
import { settingsApi } from '@/api/settings'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import HelpTip from '@/components/ui/HelpTip.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'

const files = ref<GalleryFile[]>([])
const totalSize = ref(0)
const expireHoursInput = ref(12)
const isLoading = ref(true)
const isSaving = ref(false)
const previewFile = ref<GalleryFile | null>(null)
const activeFilter = ref<'all' | 'image' | 'video'>('all')
const confirmDialog = useConfirmDialog()

const apiBaseUrl = import.meta.env.VITE_API_URL || window.location.origin

const imageCount = computed(() => files.value.filter((f: GalleryFile) => f.type === 'image').length)
const videoCount = computed(() => files.value.filter((f: GalleryFile) => f.type === 'video').length)

const filteredFiles = computed(() => {
  if (activeFilter.value === 'all') return files.value
  return files.value.filter((f: GalleryFile) => f.type === activeFilter.value)
})

function getFileUrl(url: string) {
  return `${apiBaseUrl}${url}`
}

async function loadGallery() {
  isLoading.value = true
  try {
    const data = await galleryApi.getFiles()
    files.value = data.files
    totalSize.value = data.total_size
    expireHoursInput.value = data.expire_hours
  } catch (e) {
    console.error('加载画廊失败:', e)
  } finally {
    isLoading.value = false
  }
}

async function handleSave() {
  // 校验：只允许 -1 或 >= 1 的整数
  const val = expireHoursInput.value
  if (val !== -1 && (val < 1 || !Number.isInteger(val))) {
    await confirmDialog.ask({
      title: '输入有误',
      message: '过期时间只能设置为 -1（永不删除）或 ≥ 1 的整数（小时）',
      confirmText: '知道了',
      cancelText: '取消',
    })
    return
  }

  isSaving.value = true
  try {
    // 先保存设置
    const settings = await settingsApi.get()
    settings.basic.image_expire_hours = val
    await settingsApi.update(settings)

    // 刷新列表获取最新过期状态
    const data = await galleryApi.getFiles()
    files.value = data.files
    totalSize.value = data.total_size
    expireHoursInput.value = data.expire_hours

    // 统计过期文件数
    const expiredImgs = files.value.filter((f: GalleryFile) => f.type === 'image' && f.expired).length
    const expiredVids = files.value.filter((f: GalleryFile) => f.type === 'video' && f.expired).length
    const totalExpired = expiredImgs + expiredVids

    if (totalExpired > 0) {
      // 有过期文件，询问是否立即删除
      const parts: string[] = []
      if (expiredImgs > 0) parts.push(`${expiredImgs} 张图片`)
      if (expiredVids > 0) parts.push(`${expiredVids} 个视频`)

      const doCleanup = await confirmDialog.ask({
        title: '保存成功',
        message: `检测到 ${parts.join('、')} 已过期，是否立即删除？`,
        confirmText: '立即删除',
        cancelText: '暂不删除',
      })

      if (doCleanup) {
        await galleryApi.cleanupExpired()
        await loadGallery()
      }
    }
  } catch (e) {
    console.error('保存设置失败:', e)
  } finally {
    isSaving.value = false
  }
}

async function handleDelete(file: GalleryFile) {
  const confirmed = await confirmDialog.ask({
    title: '确认删除',
    message: `确定要删除 ${file.filename} 吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
  })
  if (!confirmed) return

  try {
    await galleryApi.deleteFile(file.filename)
    files.value = files.value.filter((f: GalleryFile) => f.filename !== file.filename)
    totalSize.value -= file.size
  } catch (e) {
    console.error('删除失败:', e)
  }
}

function downloadFile(file: GalleryFile) {
  const a = document.createElement('a')
  a.href = getFileUrl(file.url)
  a.download = file.filename
  a.target = '_blank'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function openPreview(file: GalleryFile) {
  previewFile.value = file
}

function closePreview() {
  previewFile.value = null
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function formatTimeRemaining(seconds: number): string {
  if (seconds <= 0) return '已过期'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function handleImageError(event: Event) {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

onMounted(loadGallery)
</script>

<style scoped>
.gallery-page {
  padding: 0;
}

/* ===== 工具栏 ===== */
.gallery-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 24px;
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toolbar-right {
  display: flex;
  align-items: center;
}

.toolbar-stat {
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

/* ===== 筛选标签 ===== */
.filter-tabs {
  display: flex;
  gap: 4px;
  background: hsl(var(--secondary));
  border-radius: 999px;
  padding: 3px;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 14px;
  border: none;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  background: transparent;
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn.active {
  background: hsl(var(--card));
  color: hsl(var(--foreground));
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.tab-btn:hover:not(.active) {
  color: hsl(var(--foreground));
}

.tab-count {
  font-size: 10px;
  padding: 0 5px;
  border-radius: 999px;
  background: hsl(var(--border));
  color: hsl(var(--muted-foreground));
  line-height: 16px;
}

.tab-btn.active .tab-count {
  background: hsl(var(--foreground));
  color: hsl(var(--card));
}

/* ===== 过期设置框 ===== */
.expire-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  background: hsl(var(--background));
}

.expire-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.expire-input {
  width: 56px;
  padding: 4px 6px;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  font-size: 12px;
  background: hsl(var(--card));
  color: hsl(var(--foreground));
  text-align: center;
}

.expire-input:focus {
  outline: none;
  border-color: hsl(var(--foreground));
}

.expire-unit {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.btn-save {
  padding: 5px 14px;
  border: none;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  background: hsl(var(--foreground));
  color: hsl(var(--card));
  cursor: pointer;
  transition: opacity 0.15s;
  white-space: nowrap;
}

.btn-save:hover:not(:disabled) {
  opacity: 0.85;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== 加载 & 空状态 ===== */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid hsl(var(--border));
  border-top-color: hsl(var(--foreground));
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  margin-top: 12px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  color: hsl(var(--muted-foreground));
}

.empty-icon {
  width: 48px;
  height: 48px;
  opacity: 0.3;
  margin-bottom: 12px;
}

/* ===== 瀑布流 ===== */
.masonry-grid {
  columns: 2;
  column-gap: 12px;
  padding: 16px;
}

@media (min-width: 640px) {
  .masonry-grid { columns: 3; column-gap: 14px; padding: 20px; }
}

@media (min-width: 1024px) {
  .masonry-grid { columns: 4; column-gap: 16px; padding: 24px; }
}

@media (min-width: 1400px) {
  .masonry-grid { columns: 5; }
}

.masonry-item {
  break-inside: avoid;
  margin-bottom: 12px;
  border-radius: 12px;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  transition: transform 0.2s, box-shadow 0.2s;
}

.masonry-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.masonry-item.is-expired {
  opacity: 0.6;
}

/* ===== 媒体内容 ===== */
.media-wrapper {
  position: relative;
  cursor: pointer;
  overflow: hidden;
}

.media-content {
  width: 100%;
  display: block;
  min-height: 80px;
  background: hsl(var(--secondary));
  object-fit: cover;
}

.video-placeholder {
  position: relative;
}

.play-icon {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 40px;
  height: 40px;
  color: white;
  z-index: 2;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
  pointer-events: none;
}

/* ===== 悬浮操作 ===== */
.media-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 6px;
  padding: 8px;
  background: linear-gradient(180deg, rgba(0,0,0,0.3) 0%, transparent 40%);
  opacity: 0;
  transition: opacity 0.2s;
}

.media-wrapper:hover .media-overlay {
  opacity: 1;
}

.overlay-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  color: hsl(var(--foreground));
  cursor: pointer;
  transition: all 0.15s;
  backdrop-filter: blur(4px);
}

.overlay-btn.delete:hover {
  background: hsl(0 84.2% 60.2%);
  color: white;
}

.overlay-btn.download:hover {
  background: hsl(var(--foreground));
  color: hsl(var(--card));
}

.btn-icon {
  width: 16px;
  height: 16px;
}

.expired-badge {
  position: absolute;
  bottom: 8px;
  left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  background: hsl(0 84.2% 60.2%);
  color: white;
}

/* ===== 文件信息 ===== */
.file-info {
  padding: 8px 10px 10px;
}

.file-name {
  font-size: 11px;
  color: hsl(var(--foreground));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.file-countdown {
  color: hsl(25 95% 53%);
  font-weight: 500;
  cursor: help;
}

.file-type-badge {
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 600;
}

.file-type-badge.image {
  background: hsl(210 40% 96.1%);
  color: hsl(210 40% 40%);
}

.file-type-badge.video {
  background: hsl(280 40% 96.1%);
  color: hsl(280 40% 40%);
}

/* ===== Lightbox ===== */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(12px);
  padding: 24px;
}

.lightbox-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.lightbox-close {
  position: absolute;
  top: -40px;
  right: -8px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: white;
  cursor: pointer;
  transition: background 0.15s;
}

.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.3);
}

.lightbox-close svg {
  width: 20px;
  height: 20px;
}

.lightbox-media {
  max-width: 100%;
  max-height: 80vh;
  border-radius: 8px;
  object-fit: contain;
}

.lightbox-info {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.lightbox-dl-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 999px;
  background: transparent;
  color: white;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.lightbox-dl-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.6);
}

.btn-icon-sm {
  width: 14px;
  height: 14px;
}
</style>
