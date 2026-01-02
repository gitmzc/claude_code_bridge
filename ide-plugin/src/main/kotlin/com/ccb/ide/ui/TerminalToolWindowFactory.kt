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
 * Tool Window Factory that embeds terminals for Claude, Codex, and Gemini.
 *
 * Layout:
 * - Tab 1: Claude terminal
 * - Tab 2: Codex + Gemini (vertical split)
 *
 * Toolbar buttons:
 * - Restart: Restart current AI CLI
 * - Settings: Open plugin settings
 */
class TerminalToolWindowFactory : ToolWindowFactory {

    private var claudeWidget: ShellTerminalWidget? = null
    private var codexWidget: ShellTerminalWidget? = null
    private var geminiWidget: ShellTerminalWidget? = null
    private var currentProject: Project? = null
    private var executor: ScheduledExecutorService? = null

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        currentProject = project
        val settings = CcbSettings.getInstance()
        val cliPath = settings.cliPath.ifEmpty { "claude" }

        val terminalManager = TerminalToolWindowManager.getInstance(project)
        val workingDir = project.basePath ?: System.getProperty("user.home")

        executor = Executors.newSingleThreadScheduledExecutor()

        try {
            // === Tab 1: Claude ===
            createClaudeTab(project, toolWindow, terminalManager, workingDir, cliPath)

            // === Tab 2: Codex + Gemini (split) ===
            createCodexGeminiTab(project, toolWindow, terminalManager, workingDir)

        } catch (e: Exception) {
            ApplicationManager.getApplication().invokeLater {
                val errorPanel = JPanel(BorderLayout())
                errorPanel.add(JLabel("Failed to create terminal: ${e.message}"), BorderLayout.CENTER)
                val content = ContentFactory.getInstance().createContent(errorPanel, "Error", false)
                toolWindow.contentManager.addContent(content)
            }
        }
    }

    /**
     * Create Claude tab with toolbar.
     */
    private fun createClaudeTab(
        project: Project,
        toolWindow: ToolWindow,
        terminalManager: TerminalToolWindowManager,
        workingDir: String,
        cliPath: String
    ) {
        val widget = terminalManager.createLocalShellWidget(workingDir, "Claude")
        claudeWidget = widget as? ShellTerminalWidget

        val mainPanel = JPanel(BorderLayout())

        // Toolbar
        val toolbar = createToolbar(project, "claude")
        mainPanel.add(toolbar, BorderLayout.NORTH)
        mainPanel.add(widget.component, BorderLayout.CENTER)

        val content = ContentFactory.getInstance().createContent(mainPanel, "Claude", false)

        Disposer.register(content, Disposable {
            widget.close()
            claudeWidget = null
        })

        toolWindow.contentManager.addContent(content)

        // Execute claude command
        if (widget is ShellTerminalWidget) {
            executor?.schedule({
                try {
                    val safeCliPath = if (cliPath.contains(" ")) "\"$cliPath\"" else cliPath
                    widget.executeCommand(safeCliPath)
                } catch (e: Exception) {
                    com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                        .warn("Failed to execute claude command: ${e.message}")
                }
            }, 500, TimeUnit.MILLISECONDS)
        }
    }

    /**
     * Create Codex + Gemini tab with vertical split.
     */
    private fun createCodexGeminiTab(
        project: Project,
        toolWindow: ToolWindow,
        terminalManager: TerminalToolWindowManager,
        workingDir: String
    ) {
        // Create Codex widget
        val codexTerminal = terminalManager.createLocalShellWidget(workingDir, "Codex")
        codexWidget = codexTerminal as? ShellTerminalWidget

        // Create Gemini widget
        val geminiTerminal = terminalManager.createLocalShellWidget(workingDir, "Gemini")
        geminiWidget = geminiTerminal as? ShellTerminalWidget

        // Create split pane (vertical: top/bottom)
        val splitPane = JSplitPane(JSplitPane.VERTICAL_SPLIT)
        splitPane.topComponent = codexTerminal.component
        splitPane.bottomComponent = geminiTerminal.component
        splitPane.resizeWeight = 0.5 // Equal split
        splitPane.dividerSize = 5

        val mainPanel = JPanel(BorderLayout())

        // Toolbar
        val toolbar = createToolbar(project, "codex+gemini")
        mainPanel.add(toolbar, BorderLayout.NORTH)
        mainPanel.add(splitPane, BorderLayout.CENTER)

        val content = ContentFactory.getInstance().createContent(mainPanel, "Codex + Gemini", false)

        Disposer.register(content, Disposable {
            codexTerminal.close()
            geminiTerminal.close()
            codexWidget = null
            geminiWidget = null
        })

        toolWindow.contentManager.addContent(content)

        // Execute codex and gemini commands
        executor?.schedule({
            try {
                if (codexTerminal is ShellTerminalWidget) {
                    codexTerminal.executeCommand("codex")
                }
            } catch (e: Exception) {
                com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                    .warn("Failed to execute codex command: ${e.message}")
            }
        }, 500, TimeUnit.MILLISECONDS)

        executor?.schedule({
            try {
                if (geminiTerminal is ShellTerminalWidget) {
                    geminiTerminal.executeCommand("gemini")
                }
            } catch (e: Exception) {
                com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                    .warn("Failed to execute gemini command: ${e.message}")
            }
        }, 600, TimeUnit.MILLISECONDS)
    }

    /**
     * Create toolbar with action buttons.
     */
    private fun createToolbar(project: Project, mode: String): JPanel {
        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)

        // Restart button
        val restartBtn = JButton("Restart", AllIcons.Actions.Restart)
        restartBtn.toolTipText = "Restart AI CLI"
        restartBtn.addActionListener {
            when (mode) {
                "claude" -> restartClaude()
                "codex+gemini" -> restartCodexGemini()
            }
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

        toolbar.add(Box.createHorizontalGlue())

        return toolbar
    }

    /**
     * Restart Claude CLI.
     */
    private fun restartClaude() {
        val widget = claudeWidget ?: return
        val settings = CcbSettings.getInstance()
        val cliPath = settings.cliPath.ifEmpty { "claude" }

        try {
            widget.executeCommand("\u0003") // Ctrl+C
            executor?.schedule({
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
     * Restart Codex and Gemini CLIs.
     */
    private fun restartCodexGemini() {
        try {
            codexWidget?.executeCommand("\u0003")
            geminiWidget?.executeCommand("\u0003")

            executor?.schedule({
                try {
                    codexWidget?.executeCommand("codex")
                } catch (e: Exception) {
                    com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                        .warn("Failed to restart codex: ${e.message}")
                }
            }, 300, TimeUnit.MILLISECONDS)

            executor?.schedule({
                try {
                    geminiWidget?.executeCommand("gemini")
                } catch (e: Exception) {
                    com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                        .warn("Failed to restart gemini: ${e.message}")
                }
            }, 400, TimeUnit.MILLISECONDS)
        } catch (e: Exception) {
            com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                .warn("Failed to restart codex/gemini: ${e.message}")
        }
    }
}
