package com.ccb.ide.backend

import com.ccb.ide.config.CcbSettings
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessAdapter
import com.intellij.execution.process.ProcessEvent
import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Key
import java.io.OutputStreamWriter
import java.nio.charset.StandardCharsets
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Manages the Claude Code CLI process lifecycle.
 *
 * Fixed issues from code review:
 * - Thread-safe with ReentrantLock and AtomicBoolean
 * - Proper null checks before accessing outputStream
 * - Prevents duplicate starts
 * - Implements Disposable for proper cleanup
 * - Synchronized sendMessage to prevent write races
 */
class CliProcessManager(private val project: Project) : Disposable {

    private var processHandler: OSProcessHandler? = null
    private var stdinWriter: OutputStreamWriter? = null
    private var onOutput: ((String) -> Unit)? = null

    // Thread safety: prevent concurrent start/stop
    private val lock = ReentrantLock()
    private val isStarting = AtomicBoolean(false)

    fun isRunning(): Boolean = lock.withLock {
        processHandler?.isProcessTerminated == false
    }

    /**
     * Start the CLI process.
     * Thread-safe: prevents duplicate starts.
     */
    fun start(outputCallback: ((String) -> Unit)? = null) {
        // Prevent concurrent starts
        if (!isStarting.compareAndSet(false, true)) {
            return
        }

        try {
            lock.withLock {
                // Double-check: already running?
                if (processHandler?.isProcessTerminated == false) {
                    return
                }

                // Clean up any previous state
                cleanup()

                onOutput = outputCallback
                val settings = CcbSettings.getInstance()
                val cliPath = settings.cliPath.ifEmpty { "claude" }

                val commandLine = GeneralCommandLine().apply {
                    exePath = cliPath
                    // Headless mode - no TUI, stdin input
                    addParameters("--dangerously-skip-permissions")
                    workDirectory = project.basePath?.let { java.io.File(it) }
                    charset = StandardCharsets.UTF_8

                    // Pass project hash via environment variable for session alignment
                    project.basePath?.let { basePath ->
                        val hash = computeProjectHash(basePath)
                        environment["CCB_PROJECT_HASH"] = hash
                    }
                }

                val handler = OSProcessHandler(commandLine)

                handler.addProcessListener(object : ProcessAdapter() {
                    override fun onTextAvailable(event: ProcessEvent, outputType: Key<*>) {
                        onOutput?.invoke(event.text)
                    }

                    override fun processTerminated(event: ProcessEvent) {
                        lock.withLock {
                            stdinWriter?.close()
                            stdinWriter = null
                        }
                    }
                })

                handler.startNotify()
                processHandler = handler

                // Get stdin writer - with proper null check
                val outputStream = handler.process?.outputStream
                if (outputStream != null) {
                    stdinWriter = OutputStreamWriter(outputStream, StandardCharsets.UTF_8)
                } else {
                    throw RuntimeException("Failed to get process output stream")
                }
            }
        } catch (e: Exception) {
            lock.withLock {
                cleanup()
            }
            throw RuntimeException("Failed to start CLI: ${e.message}", e)
        } finally {
            isStarting.set(false)
        }
    }

    /**
     * Send a message to the CLI via stdin.
     * Thread-safe: synchronized to prevent write races.
     */
    @Synchronized
    fun sendMessage(message: String) {
        val writer = stdinWriter ?: throw IllegalStateException("CLI not running")

        try {
            writer.write(message)
            writer.write("\n")
            writer.flush()
        } catch (e: Exception) {
            throw RuntimeException("Failed to send message: ${e.message}", e)
        }
    }

    /**
     * Stop the CLI process and clean up resources.
     */
    fun stop() {
        lock.withLock {
            cleanup()
        }
    }

    /**
     * Internal cleanup - must be called within lock.
     */
    private fun cleanup() {
        try {
            stdinWriter?.close()
        } catch (e: Exception) {
            // Ignore close errors
        }
        stdinWriter = null

        try {
            processHandler?.destroyProcess()
        } catch (e: Exception) {
            // Ignore destroy errors
        }
        processHandler = null

        onOutput = null
    }

    /**
     * Compute project hash for session file alignment.
     * Must match the hash algorithm used by Claude Code CLI.
     */
    private fun computeProjectHash(basePath: String): String {
        // Simple hash - in production, should match Node.js path.resolve() behavior
        return basePath.hashCode().toString(16)
    }

    override fun dispose() {
        stop()
    }
}
