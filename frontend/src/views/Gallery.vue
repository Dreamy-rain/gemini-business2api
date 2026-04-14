<template>
  <div class="space-y-8">
    <section class="ui-panel">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="min-w-0">
          <p class="ui-section-title">媒体画廊</p>
        </div>
        <Button
          size="xs"
          variant="primary"
          root-class="min-w-14 justify-center"
          :disabled="isSaving"
          @click="handleSave"
        >
          {{ isSaving ? '保存中...' : '保存设置' }}
        </Button>
      </div>

      <div class="mt-6 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div class="flex min-w-0 flex-1 flex-wrap items-center gap-3">
          <SegmentedTabs
            v-model="activeFilter"
            :options="filterOptions"
            aria-label="媒体分类筛选"
          />

          <div class="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span class="ui-chip">总文件 {{ counts.all }}</span>
            <span class="ui-chip">总占用 {{ formatSize(totalSize) }}</span>
          </div>
        </div>

        <div class="gallery-setting-row">
          <span class="text-xs text-muted-foreground">过期时间</span>
          <Input
            :model-value="expireHoursInput"
            type="number"
            root-class="w-16 text-center"
            @update:model-value="expireHoursInput = Number($event)"
          />
          <span class="text-xs text-muted-foreground">小时</span>
          <HelpTip text="-1 表示永不自动删除；其余最小值为 1 小时。过期媒体可手动立即清理。" />
          <Button size="sm" variant="outline" @click="handleCleanupExpired">
            清理过期
          </Button>
        </div>
      </div>
    </section>

    <section class="ui-panel !p-0 overflow-hidden">
      <div class="gallery-content-toolbar">
        <div>
          <p class="ui-section-kicker">当前视图</p>
          <p class="mt-1 text-xs text-muted-foreground">{{ paginationSummary }}</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs text-muted-foreground">每页</span>
          <SegmentedTabs
            v-model="pageSize"
            :options="pageSizeOptions"
            aria-label="画廊每页数量"
          />
        </div>
      </div>

      <div v-if="!hasLoadedOnce && files.length === 0" class="gallery-state-wrap">
      </div>

      <div v-else-if="files.length === 0" class="gallery-state-wrap">
        <svg viewBox="0 0 24 24" class="h-12 w-12 text-muted-foreground/40" fill="currentColor">
          <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
        </svg>
        <p class="text-sm text-muted-foreground">暂无{{ emptyLabel }}文件</p>
      </div>

      <div v-else class="space-y-4">
        <div class="masonry-grid">
          <div
            v-for="file in files"
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
                <span>{{ formatSize(file.size) }}</span>
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

        <div class="gallery-pagination">
          <div class="text-xs text-muted-foreground">
            {{ paginationSummary }}
          </div>
          <div class="flex items-center gap-2">
            <Button
              size="xs"
              variant="outline"
              root-class="min-w-14 justify-center"
              :disabled="currentPage <= 1 || isLoading"
              @click="currentPage -= 1"
            >
              上一页
            </Button>
            <span class="ui-chip">{{ currentPage }} / {{ pageCount }}</span>
            <Button
              size="xs"
              variant="outline"
              root-class="min-w-14 justify-center"
              :disabled="currentPage >= pageCount || isLoading"
              @click="currentPage += 1"
            >
              下一页
            </Button>
          </div>
        </div>
      </div>
    </section>

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
import { computed, onActivated, onMounted, ref, watch } from 'vue'
import { galleryApi, type GalleryFile } from '@/api/gallery'
import { settingsApi } from '@/api/settings'
import {
  Button,
  ConfirmDialog,
  HelpTip,
  Input,
  SegmentedTabs,
  Tooltip,
} from 'nanocat-ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'

const apiBaseUrl = import.meta.env.VITE_API_URL || window.location.origin
const toast = useToast()
const confirmDialog = useConfirmDialog()

const allFiles = ref<GalleryFile[]>([])
const totalSize = ref(0)
const lastLoadedAt = ref(0)
const expireHoursInput = ref(12)
const isLoading = ref(true)
const hasLoadedOnce = ref(false)
const isSaving = ref(false)
const previewFile = ref<GalleryFile | null>(null)
const activeFilter = ref<'all' | 'image' | 'video'>('all')
const pageSize = ref(24)
const currentPage = ref(1)

const pageSizeOptions = [
  { label: '24', value: 24 },
  { label: '48', value: 48 },
  { label: '96', value: 96 },
]

const counts = computed(() => {
  const image = allFiles.value.filter((item) => item.type === 'image').length
  const video = allFiles.value.filter((item) => item.type === 'video').length
  return {
    all: allFiles.value.length,
    image,
    video,
  }
})

const filterOptions = computed(() => [
  { label: '全部', value: 'all', count: counts.value.all },
  { label: '图片', value: 'image', count: counts.value.image },
  { label: '视频', value: 'video', count: counts.value.video },
])

const filteredFiles = computed(() => {
  if (activeFilter.value === 'all') return allFiles.value
  return allFiles.value.filter((item) => item.type === activeFilter.value)
})

const totalItems = computed(() => filteredFiles.value.length)
const pageCount = computed(() => Math.max(1, Math.ceil(totalItems.value / pageSize.value)))

const files = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredFiles.value.slice(start, start + pageSize.value)
})

const emptyLabel = computed(() => {
  switch (activeFilter.value) {
    case 'image':
      return '图片'
    case 'video':
      return '视频'
    default:
      return '媒体'
  }
})

const paginationSummary = computed(() => `第 ${currentPage.value} / ${pageCount.value} 页，共 ${totalItems.value} 项`)

function getFileUrl(url: string) {
  return `${apiBaseUrl}${url}`
}

async function loadGallery() {
  isLoading.value = true
  try {
    const data = await galleryApi.getFiles()
    allFiles.value = data.files || []
    totalSize.value = data.total_size || 0
    expireHoursInput.value = data.expire_hours
    if (currentPage.value > pageCount.value) {
      currentPage.value = pageCount.value
    }
    lastLoadedAt.value = Date.now()
  } catch (error: any) {
    toast.error(error?.message || '加载画廊失败', '加载失败')
  } finally {
    isLoading.value = false
    hasLoadedOnce.value = true
  }
}

async function handleSave() {
  const val = expireHoursInput.value
  if (val !== -1 && (val < 1 || !Number.isInteger(val))) {
    toast.warning('过期时间只能设置为 -1 或大于等于 1 的整数小时。', '输入有误')
    return
  }

  isSaving.value = true
  try {
    const settings = await settingsApi.get()
    settings.basic.image_expire_hours = val
    await settingsApi.update(settings)
    await loadGallery()
    toast.success('画廊过期设置已保存。', '保存成功')
  } catch (error: any) {
    toast.error(error?.message || '保存画廊设置失败', '保存失败')
  } finally {
    isSaving.value = false
  }
}

async function handleCleanupExpired() {
  const confirmed = await confirmDialog.ask({
    title: '确认清理',
    message: '确定要立即清理所有已过期媒体吗？此操作不可恢复。',
    confirmText: '立即清理',
    cancelText: '取消',
  })
  if (!confirmed) return

  try {
    const result = await galleryApi.cleanupExpired()
    await loadGallery()
    toast.success(result.message || '已完成过期媒体清理。', '清理完成')
  } catch (error: any) {
    toast.error(error?.message || '清理过期媒体失败', '清理失败')
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
    allFiles.value = allFiles.value.filter((item) => item.filename !== file.filename)
    totalSize.value = Math.max(0, totalSize.value - file.size)
    if (currentPage.value > pageCount.value) {
      currentPage.value = pageCount.value
    }
    toast.success(`已删除 ${file.filename}`, '删除成功')
  } catch (error: any) {
    toast.error(error?.message || '删除媒体失败', '删除失败')
  }
}

function downloadFile(file: GalleryFile) {
  const anchor = document.createElement('a')
  anchor.href = getFileUrl(file.url)
  anchor.download = file.filename
  anchor.target = '_blank'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
}

function openPreview(file: GalleryFile) {
  previewFile.value = file
}

function closePreview() {
  previewFile.value = null
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatTimeRemaining(seconds: number): string {
  if (seconds <= 0) return '已过期'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function handleImageError(event: Event) {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

watch([activeFilter, pageSize], () => {
  currentPage.value = 1
})

watch(filteredFiles, () => {
  if (currentPage.value > pageCount.value) {
    currentPage.value = pageCount.value
  }
})

onMounted(() => {
  void loadGallery()
})

onActivated(() => {
  if (!lastLoadedAt.value || Date.now() - lastLoadedAt.value > 30000) {
    void loadGallery()
  }
})
</script>

<style scoped>
.gallery-setting-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.gallery-content-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--card));
}

.gallery-state-wrap {
  display: flex;
  min-height: 360px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
}

.masonry-grid {
  columns: 2;
  column-gap: 12px;
  padding: 20px;
}

@media (min-width: 640px) {
  .masonry-grid {
    columns: 3;
    column-gap: 14px;
  }
}

@media (min-width: 1024px) {
  .masonry-grid {
    columns: 4;
    column-gap: 16px;
    padding: 24px;
  }
}

@media (min-width: 1400px) {
  .masonry-grid {
    columns: 5;
  }
}

.masonry-item {
  break-inside: avoid;
  margin-bottom: 14px;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 18px;
  background: hsl(var(--card));
  transition: transform 0.2s, box-shadow 0.2s;
}

.masonry-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.08);
}

.masonry-item.is-expired {
  opacity: 0.6;
}

.media-wrapper {
  position: relative;
  overflow: hidden;
  cursor: pointer;
}

.media-content {
  display: block;
  width: 100%;
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
  z-index: 2;
  width: 40px;
  height: 40px;
  transform: translate(-50%, -50%);
  color: white;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
  pointer-events: none;
}

.media-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 6px;
  padding: 8px;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.3) 0%, transparent 40%);
  opacity: 0;
  transition: opacity 0.2s;
}

.media-wrapper:hover .media-overlay {
  opacity: 1;
}

.overlay-btn {
  display: flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
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
  background: hsl(0 84.2% 60.2%);
  font-size: 10px;
  font-weight: 600;
  color: white;
}

.file-info {
  padding: 10px 12px 12px;
}

.file-name {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: hsl(var(--foreground));
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.file-countdown {
  color: hsl(25 95% 53%);
  font-weight: 500;
  cursor: help;
}

.file-type-badge {
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
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

.gallery-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 20px 20px;
}

.lightbox {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(12px);
}

.lightbox-content {
  position: relative;
  display: flex;
  max-width: 90vw;
  max-height: 90vh;
  flex-direction: column;
  align-items: center;
}

.lightbox-close {
  position: absolute;
  top: -40px;
  right: -8px;
  display: flex;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 999px;
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
  flex-wrap: wrap;
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
