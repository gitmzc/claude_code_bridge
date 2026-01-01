package com.ccb.ide.backend

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileContentChangeEvent
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.util.messages.MessageBusConnection
import java.io.File
import java.nio.charset.StandardCharsets
import java.nio.file.Paths
import java.util.Timer
import java.util.TimerTask
import java.util.concurrent.ConcurrentHashMap

/**
 * Watches for changes to AI session files and notifies when new messages arrive.
 *
 * Fixed issues from code review:
 * - Uses Gson for proper JSON parsing (not regex)
 * - Full file reading (JSON is rewritten, not appended)
 * - Active VFS refresh via Timer (not just passive listening)
 * - Thread-safe with ConcurrentHashMap
 * - Handles file truncation/rewrite scenarios
 */
class FileWatcherService(
    private val project: Project,
    private val onMessage: (String) -> Unit
) : Disposable {

    private var connection: MessageBusConnection? = null
    private var refreshTimer: Timer? = null
    private val watchedPaths: MutableSet<String> = mutableSetOf()

    // Track last seen message count to detect new messages (thread-safe)
    private val lastSeenMessageCounts: ConcurrentHashMap<String, Int> = ConcurrentHashMap()

    companion object {
        private const val REFRESH_INTERVAL_MS = 500L // Active refresh every 500ms
    }

    @Synchronized
    fun startWatching() {
        if (connection != null) return

        val homePath = System.getProperty("user.home")

        // Gemini session path
        val geminiPath = Paths.get(homePath, ".gemini", "tmp").toString()

        // Codex session path
        val codexPath = Paths.get(homePath, ".codex", "sessions").toString()

        // Add paths to watch
        listOf(geminiPath, codexPath).forEach { path ->
            val file = File(path)
            if (file.exists()) {
                LocalFileSystem.getInstance().addRootToWatch(path, true)
                watchedPaths.add(path)
            }
        }

        // Subscribe to file change events (passive listening)
        connection = project.messageBus.connect().apply {
            subscribe(VirtualFileManager.VFS_CHANGES, object : BulkFileListener {
                override fun after(events: List<VFileEvent>) {
                    events.filterIsInstance<VFileContentChangeEvent>()
                        .filter { isWatchedFile(it.file) }
                        .forEach { event ->
                            // Handle in background thread to avoid blocking EDT
                            ApplicationManager.getApplication().executeOnPooledThread {
                                handleFileChange(event.file)
                            }
                        }
                }
            })
        }

        // Start active refresh timer (critical for real-time updates)
        refreshTimer = Timer("CCB-VFS-Refresh", true).apply {
            scheduleAtFixedRate(object : TimerTask() {
                override fun run() {
                    refreshWatchedPaths()
                }
            }, REFRESH_INTERVAL_MS, REFRESH_INTERVAL_MS)
        }
    }

    @Synchronized
    fun stopWatching() {
        refreshTimer?.cancel()
        refreshTimer = null

        connection?.disconnect()
        connection = null

        watchedPaths.clear()
        lastSeenMessageCounts.clear()
    }

    /**
     * Actively refresh VFS to detect external file changes.
     * This is critical because VFS is async and may not detect changes immediately.
     */
    private fun refreshWatchedPaths() {
        watchedPaths.forEach { path ->
            val virtualFile = LocalFileSystem.getInstance().findFileByPath(path)
            if (virtualFile != null) {
                VfsUtil.markDirtyAndRefresh(true, true, true, virtualFile)
            }
        }
    }

    private fun isWatchedFile(file: VirtualFile?): Boolean {
        if (file == null) return false
        val path = file.path

        return (path.contains(".gemini") && path.endsWith(".json")) ||
               (path.contains(".codex") && path.endsWith(".jsonl"))
    }

    private fun handleFileChange(file: VirtualFile) {
        try {
            val path = file.path

            // Full file read (JSON is rewritten, not appended)
            val content = file.contentsToByteArray().toString(StandardCharsets.UTF_8)

            if (content.isEmpty()) return

            // Parse and extract new AI messages
            val newMessages = when {
                path.contains(".gemini") -> parseGeminiSession(content, path)
                path.contains(".codex") -> parseCodexSession(content, path)
                else -> emptyList()
            }

            // Notify for each new message
            newMessages.forEach { message ->
                if (message.isNotEmpty()) {
                    onMessage(message)
                }
            }
        } catch (e: Exception) {
            System.err.println("Error reading session file: ${e.message}")
        }
    }

    /**
     * Parse Gemini session JSON and extract new assistant messages.
     * Uses Gson for proper JSON parsing.
     */
    private fun parseGeminiSession(content: String, path: String): List<String> {
        val newMessages = mutableListOf<String>()

        try {
            val json = JsonParser.parseString(content)

            // Gemini session format: { "messages": [...] } or just [...]
            val messages: JsonArray = when {
                json.isJsonArray -> json.asJsonArray
                json.isJsonObject && json.asJsonObject.has("messages") ->
                    json.asJsonObject.getAsJsonArray("messages")
                else -> return emptyList()
            }

            // Find new model messages (handle file rewrite/truncation)
            val currentCount = messages.size()
            val lastCount = lastSeenMessageCounts.getOrDefault(path, 0)

            // Reset if file was truncated/rewritten with fewer messages
            if (currentCount < lastCount) {
                lastSeenMessageCounts[path] = 0
                return emptyList() // Skip this cycle, will catch up next time
            }

            if (currentCount > lastCount) {
                // Process only new messages
                for (i in lastCount until currentCount) {
                    val msg = messages[i].asJsonObject
                    val role = msg.get("role")?.asString

                    if (role == "model" || role == "assistant") {
                        val text = extractTextFromMessage(msg)
                        if (text.isNotEmpty()) {
                            newMessages.add(text)
                        }
                    }
                }
                lastSeenMessageCounts[path] = currentCount
            }
        } catch (e: Exception) {
            System.err.println("Error parsing Gemini session: ${e.message}")
        }

        return newMessages
    }

    /**
     * Parse Codex session JSONL and extract new assistant messages.
     */
    private fun parseCodexSession(content: String, path: String): List<String> {
        val newMessages = mutableListOf<String>()

        try {
            val lines = content.lines().filter { it.isNotBlank() }
            val currentCount = lines.size
            val lastCount = lastSeenMessageCounts.getOrDefault(path, 0)

            // Reset if file was truncated/rewritten with fewer lines
            if (currentCount < lastCount) {
                lastSeenMessageCounts[path] = 0
                return emptyList() // Skip this cycle, will catch up next time
            }

            if (currentCount > lastCount) {
                // Process only new lines
                for (i in lastCount until currentCount) {
                    val line = lines[i]
                    try {
                        val json = JsonParser.parseString(line).asJsonObject
                        val role = json.get("role")?.asString

                        if (role == "assistant") {
                            val text = extractTextFromMessage(json)
                            if (text.isNotEmpty()) {
                                newMessages.add(text)
                            }
                        }
                    } catch (e: Exception) {
                        // Skip malformed lines
                    }
                }
                lastSeenMessageCounts[path] = currentCount
            }
        } catch (e: Exception) {
            System.err.println("Error parsing Codex session: ${e.message}")
        }

        return newMessages
    }

    /**
     * Extract text content from a message JSON object.
     * Handles various formats: { "text": "..." }, { "content": "..." }, { "parts": [...] }
     */
    private fun extractTextFromMessage(msg: JsonObject): String {
        // Try "text" field
        msg.get("text")?.let {
            if (it.isJsonPrimitive) return it.asString
        }

        // Try "content" field
        msg.get("content")?.let {
            if (it.isJsonPrimitive) return it.asString
            if (it.isJsonArray) {
                // Content array format: [{ "type": "text", "text": "..." }]
                return it.asJsonArray
                    .filter { part -> part.isJsonObject }
                    .mapNotNull { part ->
                        val partObj = part.asJsonObject
                        if (partObj.get("type")?.asString == "text") {
                            partObj.get("text")?.asString
                        } else null
                    }
                    .joinToString("\n")
            }
        }

        // Try "parts" field (Gemini format)
        msg.get("parts")?.let {
            if (it.isJsonArray) {
                return it.asJsonArray
                    .filter { part -> part.isJsonObject }
                    .mapNotNull { part -> part.asJsonObject.get("text")?.asString }
                    .joinToString("\n")
            }
        }

        return ""
    }

    override fun dispose() {
        stopWatching()
    }
}
