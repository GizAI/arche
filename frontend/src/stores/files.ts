import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export interface FileItem {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number
  modified?: string
  children?: FileItem[]
}

export interface FileTree {
  root: string
  items: FileItem[]
}

export const useFilesStore = defineStore('files', () => {
  const tree = ref<FileTree | null>(null)
  const currentFile = ref<{ path: string; content: string } | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchTree() {
    loading.value = true
    error.value = null
    try {
      const res = await axios.get('/api/files')
      tree.value = res.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to fetch files'
    } finally {
      loading.value = false
    }
  }

  async function readFile(path: string) {
    loading.value = true
    error.value = null
    try {
      const res = await axios.get(`/api/files/${encodeURIComponent(path)}`)
      currentFile.value = res.data
      return currentFile.value
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to read file'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function writeFile(path: string, content: string) {
    loading.value = true
    error.value = null
    try {
      await axios.put(`/api/files/${encodeURIComponent(path)}`, { path, content })
      return true
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to write file'
      throw e
    } finally {
      loading.value = false
    }
  }

  // Helper to get files by directory type
  function getFilesByDir(dirName: string): FileItem[] {
    if (!tree.value) return []
    const dir = tree.value.items.find(i => i.name === dirName && i.type === 'directory')
    return dir?.children?.filter(c => c.type === 'file') ?? []
  }

  return {
    tree,
    currentFile,
    loading,
    error,
    fetchTree,
    readFile,
    writeFile,
    getFilesByDir,
  }
})
