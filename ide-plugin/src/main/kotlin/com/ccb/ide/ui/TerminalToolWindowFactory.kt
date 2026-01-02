package com.ccb.ide.ui

import com.ccb.ide.config.CcbSettings
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import org.jetbrains.plugins.terminal.ShellTerminalWidget
import org.jetbrains.plugins.terminal.TerminalToolWindowManager
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import javax.swing.JLabel
import javax.swing.JPanel
import java.awt.BorderLayout

/**
 * Tool Window Factory that embeds a terminal running Claude Code CLI.
 *
 * This provides the full TUI experience of Claude Code within the IDE,
 * including session persistence, tool calls, and interactive features.
 */
class TerminalToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val settings = CcbSettings.getInstance()
        val cliPath = settings.cliPath.ifEmpty { "claude" }

        // Get the terminal manager
        val terminalManager = TerminalToolWindowManager.getInstance(project)

        // Create a new terminal tab with Claude Code
        val workingDir = project.basePath ?: System.getProperty("user.home")

        try {
            // Create terminal widget
            val widget = terminalManager.createLocalShellWidget(workingDir, "Claude Code")

            // Add widget's component to the tool window
            val content = ContentFactory.getInstance().createContent(
                widget.component,
                "Claude Code",
                false
            )

            // Create executor for delayed command execution
            val executor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()

            // Register disposable for cleanup (widget + executor)
            Disposer.register(content, Disposable {
                executor.shutdownNow()
                widget.close()
            })

            toolWindow.contentManager.addContent(content)

            // Execute claude command after shell is ready
            if (widget is ShellTerminalWidget) {
                executor.schedule({
                    try {
                        // Quote the path if it contains spaces
                        val safeCliPath = if (cliPath.contains(" ")) "\"$cliPath\"" else cliPath
                        widget.executeCommand(safeCliPath)
                    } catch (e: Exception) {
                        // Log error but don't crash
                        com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                            .warn("Failed to execute claude command: ${e.message}")
                    }
                }, 500, TimeUnit.MILLISECONDS)
            }
        } catch (e: Exception) {
            // Fallback: show error message if terminal creation fails (on EDT)
            ApplicationManager.getApplication().invokeLater {
                val errorPanel = JPanel(BorderLayout())
                errorPanel.add(JLabel("Failed to create terminal: ${e.message}"), BorderLayout.CENTER)
                val content = ContentFactory.getInstance().createContent(errorPanel, "Error", false)
                toolWindow.contentManager.addContent(content)
            }
        }
    }
}
