package com.ccb.ide.backend

import com.ccb.ide.config.CcbSettings
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessAdapter
import com.intellij.execution.process.ProcessEvent
import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Key
import java.nio.charset.StandardCharsets
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Manages the Claude Code CLI process lifecycle.
 *
 * Simplified design: Each message spawns a new CLI process with --print mode.
 * This avoids the complexity of stream-json I/O while still providing
 * real-time output streaming.
 */
class CliProcessManager(private val project: Project) : Disposable {

    private var currentProcess: OSProcessHandler? = null
    private val isProcessing = AtomicBoolean(false)

    fun isRunning(): Boolean = isProcessing.get()

    /**
     * Send a message to Claude Code CLI.
     * Spawns a new process for each message.
     */
    fun sendMessage(message: String, outputCallback: (String) -> Unit) {
        if (!isProcessing.compareAndSet(false, true)) {
            outputCallback("[Error] A request is already in progress\n")
            return
        }

        try {
            val settings = CcbSettings.getInstance()
            val cliPath = settings.cliPath.ifEmpty { "claude" }

            val commandLine = GeneralCommandLine().apply {
                exePath = cliPath
                addParameters(
                    "--print",                          // Non-interactive, print output
                    "--dangerously-skip-permissions",   // Skip permission prompts
                    message                             // The prompt as argument
                )
                workDirectory = project.basePath?.let { java.io.File(it) }
                charset = StandardCharsets.UTF_8
            }

            val handler = OSProcessHandler(commandLine)
            currentProcess = handler

            handler.addProcessListener(object : ProcessAdapter() {
                override fun onTextAvailable(event: ProcessEvent, outputType: Key<*>) {
                    outputCallback(event.text)
                }

                override fun processTerminated(event: ProcessEvent) {
                    isProcessing.set(false)
                    currentProcess = null
                }
            })

            handler.startNotify()

        } catch (e: Exception) {
            isProcessing.set(false)
            outputCallback("[Error] Failed to start CLI: ${e.message}\n")
        }
    }

    /**
     * Stop the current CLI process.
     */
    fun stop() {
        currentProcess?.destroyProcess()
        currentProcess = null
        isProcessing.set(false)
    }

    override fun dispose() {
        stop()
    }
}
