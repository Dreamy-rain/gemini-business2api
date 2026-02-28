import apiClient from './client'

export interface GalleryFile {
    filename: string
    url: string
    size: number
    created_at: string
    mtime: number
    type: 'image' | 'video'
    expired: boolean
    expires_in_seconds: number | null
}

export interface GalleryResponse {
    files: GalleryFile[]
    total: number
    total_size: number
    expire_hours: number
}

export const galleryApi = {
    // 获取画廊文件列表
    getFiles: () =>
        apiClient.get<never, GalleryResponse>('/admin/gallery'),

    // 删除单个文件
    deleteFile: (filename: string) =>
        apiClient.delete(`/admin/gallery/${filename}`),

    // 立即清理过期文件
    cleanupExpired: () =>
        apiClient.post<never, { success: boolean; deleted: number; message: string }>('/admin/gallery/cleanup'),
}
