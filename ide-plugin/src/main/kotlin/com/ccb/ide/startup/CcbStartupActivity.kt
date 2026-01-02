package com.ccb.ide.startup

import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.intellij.openapi.wm.ToolWindowManager

/**
 * Automatically opens the Claude Code Bridge tool window when a project is opened.
 */
class CcbStartupActivity : ProjectActivity {

    override suspend fun execute(project: Project) {
        // Open tool window after project is fully loaded
        val toolWindowManager = ToolWindowManager.getInstance(project)
        val toolWindow = toolWindowManager.getToolWindow("Claude Code Bridge")
        toolWindow?.show()
    }
}
