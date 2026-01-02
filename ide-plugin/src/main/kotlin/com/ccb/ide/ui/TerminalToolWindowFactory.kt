package com.ccb.ide.ui

import com.ccb.ide.config.CcbSettings
import com.intellij.icons.AllIcons
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.options.ShowSettingsUtil
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
import javax.swing.*
import java.awt.BorderLayout

/**
 * Tool Window Factory that embeds a terminal running Claude Code CLI.
 *
 * This provides the full TUI experience of Claude Code within the IDE,
 * including session persistence, tool calls, and interactive features.
 *
 * Toolbar buttons:
 * - Restart Claude: Restart the claude CLI
 * - Settings: Open plugin settings
 * - Codex: Open Codex in new terminal tab
 * - Gemini: Open Gemini in new terminal tab
 */
class TerminalToolWindowFactory : ToolWindowFactory {

    private var currentWidget: ShellTerminalWidget? = null
    private var currentProject: Project? = null
    private var currentExecutor: ScheduledExecutorService? = null

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        currentProject = project
        val settings = CcbSettings.getInstance()
        val cliPath = settings.cliPath.ifEmpty { "claude" }

        // Get the terminal manager
        val terminalManager = TerminalToolWindowManager.getInstance(project)

        // Create a new terminal tab with Claude Code
        val workingDir = project.basePath ?: System.getProperty("user.home")

        try {
            // Create terminal widget
            val widget = terminalManager.createLocalShellWidget(workingDir, "Claude Code")
            currentWidget = widget as? ShellTerminalWidget

            // Create main panel with toolbar
            val mainPanel = JPanel(BorderLayout())

            // Create toolbar
            val toolbar = createToolbar(project, toolWindow, terminalManager, workingDir)
            mainPanel.add(toolbar, BorderLayout.NORTH)

            // Add terminal widget
            mainPanel.add(widget.component, BorderLayout.CENTER)

            // Add panel to the tool window
            val content = ContentFactory.getInstance().createContent(
                mainPanel,
                "Claude Code",
                false
            )

            // Create executor for delayed command execution
            val executor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
            currentExecutor = executor

            // Register disposable for cleanup (widget + executor)
            Disposer.register(content, Disposable {
                executor.shutdownNow()
                widget.close()
                currentWidget = null
                currentExecutor = null
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

    /**
     * Create toolbar with action buttons.
     */
    private fun createToolbar(
        project: Project,
        toolWindow: ToolWindow,
        terminalManager: TerminalToolWindowManager,
        workingDir: String
    ): JPanel {
        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)

        // Restart Claude button
        val restartBtn = JButton("Restart", AllIcons.Actions.Restart)
        restartBtn.toolTipText = "Restart Claude CLI"
        restartBtn.addActionListener {
            restartClaude()
        }
        toolbar.add(restartBtn)

        toolbar.add(Box.createHorizontalStrut(5))

        // Settings button
        val settingsBtn = JButton("Settings", AllIcons.General.Settings)
        settingsBtn.toolTipText = "Open Claude Code Bridge Settings"
        settingsBtn.addActionListener {
            ShowSettingsUtil.getInstance().showSettingsDialog(project, "Claude Code Bridge")
        }
        toolbar.add(settingsBtn)

        toolbar.add(Box.createHorizontalStrut(10))
        toolbar.add(JSeparator(SwingConstants.VERTICAL))
        toolbar.add(Box.createHorizontalStrut(10))

        // Codex button
        val codexBtn = JButton("Codex", AllIcons.Nodes.Console)
        codexBtn.toolTipText = "Open Codex via CCB (in WezTerm)"
        codexBtn.addActionListener {
            launchCcbCommand("ccb up codex")
        }
        toolbar.add(codexBtn)

        toolbar.add(Box.createHorizontalStrut(5))

        // Gemini button
        val geminiBtn = JButton("Gemini", AllIcons.Nodes.Console)
        geminiBtn.toolTipText = "Open Gemini via CCB (in WezTerm)"
        geminiBtn.addActionListener {
            launchCcbCommand("ccb up gemini")
        }
        toolbar.add(geminiBtn)

        toolbar.add(Box.createHorizontalGlue())

        return toolbar
    }

    /**
     * Restart Claude CLI in the current terminal.
     */
    private fun restartClaude() {
        val widget = currentWidget ?: return
        val settings = CcbSettings.getInstance()
        val cliPath = settings.cliPath.ifEmpty { "claude" }

        try {
            // Send Ctrl+C to stop current process, then restart
            widget.executeCommand("\u0003") // Ctrl+C
            currentExecutor?.schedule({
                try {
                    val safeCliPath = if (cliPath.contains(" ")) "\"$cliPath\"" else cliPath
                    widget.executeCommand(safeCliPath)
                } catch (e: Exception) {
                    com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                        .warn("Failed to restart claude: ${e.message}")
                }
            }, 300, TimeUnit.MILLISECONDS)
        } catch (e: Exception) {
            com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                .warn("Failed to restart claude: ${e.message}")
        }
    }

    /**
     * Launch a CCB command in the background (opens in WezTerm).
     */
    private fun launchCcbCommand(command: String) {
        val workingDir = currentProject?.basePath ?: System.getProperty("user.home")
        try {
            val processBuilder = ProcessBuilder("bash", "-c", command)
            processBuilder.directory(java.io.File(workingDir))
            processBuilder.start()
        } catch (e: Exception) {
            com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                .warn("Failed to launch CCB command: ${e.message}")
        }
    }

    /**
     * Open a new terminal tab for another AI (Codex or Gemini).
     */
    private fun openAITerminal(
        toolWindow: ToolWindow,
        terminalManager: TerminalToolWindowManager,
        workingDir: String,
        tabName: String,
        command: String
    ) {
        try {
            val widget = terminalManager.createLocalShellWidget(workingDir, tabName)

            val content = ContentFactory.getInstance().createContent(
                widget.component,
                tabName,
                false
            )

            val executor = Executors.newSingleThreadScheduledExecutor()

            Disposer.register(content, Disposable {
                executor.shutdownNow()
                widget.close()
            })

            toolWindow.contentManager.addContent(content)
            toolWindow.contentManager.setSelectedContent(content)

            // Execute AI command after shell is ready
            if (widget is ShellTerminalWidget) {
                executor.schedule({
                    try {
                        widget.executeCommand(command)
                    } catch (e: Exception) {
                        com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                            .warn("Failed to execute $command: ${e.message}")
                    }
                }, 500, TimeUnit.MILLISECONDS)
            }
        } catch (e: Exception) {
            com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                .warn("Failed to create $tabName terminal: ${e.message}")
        }
    }
}
