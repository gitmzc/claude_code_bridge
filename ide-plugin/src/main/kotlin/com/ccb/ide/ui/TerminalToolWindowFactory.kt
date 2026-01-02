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
 * Tool Window Factory that embeds Claude terminal in IDE.
 *
 * Mixed mode:
 * - Claude runs in IDE embedded terminal (manual start)
 * - Codex + Gemini run in WezTerm (new tab with split)
 *
 * This allows cask-w/gask-w communication to work properly since
 * Codex and Gemini are in WezTerm panes.
 */
class TerminalToolWindowFactory : ToolWindowFactory {

    private var claudeWidget: ShellTerminalWidget? = null
    private var currentProject: Project? = null
    private var executor: ScheduledExecutorService? = null

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        currentProject = project

        val terminalManager = TerminalToolWindowManager.getInstance(project)
        val workingDir = project.basePath ?: System.getProperty("user.home")

        executor = Executors.newSingleThreadScheduledExecutor()

        try {
            // Create Claude terminal (but don't start claude automatically)
            val widget = terminalManager.createLocalShellWidget(workingDir, "Claude")
            claudeWidget = widget as? ShellTerminalWidget

            val mainPanel = JPanel(BorderLayout())

            // Toolbar
            val toolbar = createToolbar(project, workingDir)
            mainPanel.add(toolbar, BorderLayout.NORTH)
            mainPanel.add(widget.component, BorderLayout.CENTER)

            val content = ContentFactory.getInstance().createContent(mainPanel, "Claude", false)

            Disposer.register(content, Disposable {
                executor?.shutdownNow()
                widget.close()
                claudeWidget = null
            })

            toolWindow.contentManager.addContent(content)

            // Don't auto-start Claude - wait for user to click button

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
     * Create toolbar with action buttons.
     */
    private fun createToolbar(project: Project, workingDir: String): JPanel {
        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)

        // Start Claude button
        val startBtn = JButton("Start Claude", AllIcons.Actions.Execute)
        startBtn.toolTipText = "Start Claude CLI"
        startBtn.addActionListener {
            startClaude(false)
        }
        toolbar.add(startBtn)

        toolbar.add(Box.createHorizontalStrut(5))

        // Resume Claude button
        val resumeBtn = JButton("Resume", AllIcons.Actions.Resume)
        resumeBtn.toolTipText = "Resume last Claude session"
        resumeBtn.addActionListener {
            startClaude(true)
        }
        toolbar.add(resumeBtn)

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

        // Launch Codex + Gemini button (in WezTerm new tab with split)
        val launchBtn = JButton("Launch Codex + Gemini", AllIcons.Nodes.Console)
        launchBtn.toolTipText = "Launch Codex and Gemini in WezTerm (new tab with split)"
        launchBtn.addActionListener {
            launchCodexGemini(workingDir, false)
        }
        toolbar.add(launchBtn)

        toolbar.add(Box.createHorizontalStrut(5))

        // Resume Codex + Gemini button
        val resumeAIBtn = JButton("Resume AI", AllIcons.Actions.Resume)
        resumeAIBtn.toolTipText = "Resume last Codex and Gemini sessions"
        resumeAIBtn.addActionListener {
            launchCodexGemini(workingDir, true)
        }
        toolbar.add(resumeAIBtn)

        toolbar.add(Box.createHorizontalGlue())

        return toolbar
    }

    /**
     * Start Claude CLI.
     */
    private fun startClaude(resume: Boolean) {
        val widget = claudeWidget ?: return
        val settings = CcbSettings.getInstance()
        val cliPath = settings.cliPath.ifEmpty { "claude" }

        try {
            // Send Ctrl+C first to ensure clean state
            widget.executeCommand("\u0003")
            executor?.schedule({
                try {
                    val safeCliPath = if (cliPath.contains(" ")) "\"$cliPath\"" else cliPath
                    val cmd = if (resume) "$safeCliPath --continue" else safeCliPath
                    widget.executeCommand(cmd)
                } catch (e: Exception) {
                    com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                        .warn("Failed to start claude: ${e.message}")
                }
            }, 300, TimeUnit.MILLISECONDS)
        } catch (e: Exception) {
            com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                .warn("Failed to start claude: ${e.message}")
        }
    }

    /**
     * Launch Codex and Gemini in WezTerm new tab with split.
     * Uses CCB_NEW_TAB=1 to open in new tab, then split for second provider.
     */
    private fun launchCodexGemini(workingDir: String, resume: Boolean) {
        try {
            // Show notification that we're launching
            com.intellij.notification.NotificationGroupManager.getInstance()
                .getNotificationGroup("Claude Code Bridge")
                ?.createNotification(
                    if (resume) "Resuming Codex + Gemini..." else "Launching Codex + Gemini in WezTerm...",
                    com.intellij.notification.NotificationType.INFORMATION
                )
                ?.notify(currentProject)

            // Use full path for ccb and add -r flag for resume
            val home = System.getProperty("user.home")
            val ccbPath = "$home/.local/bin/ccb"
            val resumeFlag = if (resume) " -r" else ""
            val processBuilder = ProcessBuilder(
                "zsh", "-l", "-c",
                "CCB_NEW_TAB=1 $ccbPath up codex gemini --no-claude$resumeFlag"
            )
            processBuilder.directory(java.io.File(workingDir))
            processBuilder.redirectErrorStream(true)
            val process = processBuilder.start()

            // Log output in background thread
            Thread {
                try {
                    val output = process.inputStream.bufferedReader().readText()
                    val exitCode = process.waitFor()

                    com.intellij.openapi.application.ApplicationManager.getApplication().invokeLater {
                        if (exitCode == 0) {
                            com.intellij.notification.NotificationGroupManager.getInstance()
                                .getNotificationGroup("Claude Code Bridge")
                                ?.createNotification(
                                    "Codex + Gemini launched successfully!",
                                    com.intellij.notification.NotificationType.INFORMATION
                                )
                                ?.notify(currentProject)
                        } else {
                            com.intellij.notification.NotificationGroupManager.getInstance()
                                .getNotificationGroup("Claude Code Bridge")
                                ?.createNotification(
                                    "Failed to launch: $output",
                                    com.intellij.notification.NotificationType.ERROR
                                )
                                ?.notify(currentProject)
                        }
                    }

                    if (output.isNotBlank()) {
                        com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                            .info("CCB launch output: $output")
                    }
                } catch (e: Exception) {
                    com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                        .warn("CCB launch error: ${e.message}")
                }
            }.start()
        } catch (e: Exception) {
            com.intellij.openapi.diagnostic.Logger.getInstance(TerminalToolWindowFactory::class.java)
                .warn("Failed to launch Codex + Gemini: ${e.message}")

            com.intellij.notification.NotificationGroupManager.getInstance()
                .getNotificationGroup("Claude Code Bridge")
                ?.createNotification(
                    "Failed to launch: ${e.message}",
                    com.intellij.notification.NotificationType.ERROR
                )
                ?.notify(currentProject)
        }
    }
}
