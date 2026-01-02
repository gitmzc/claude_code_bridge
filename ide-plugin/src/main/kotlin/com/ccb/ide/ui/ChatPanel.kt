package com.ccb.ide.ui

import com.ccb.ide.backend.CliProcessManager
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import java.awt.BorderLayout
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import javax.swing.*

class ChatPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val messagesArea = JBTextArea().apply {
        isEditable = false
        lineWrap = true
        wrapStyleWord = true
    }

    private val inputField = JBTextArea(3, 40).apply {
        lineWrap = true
        wrapStyleWord = true
    }

    private val sendButton = JButton("Send")
    private val stopButton = JButton("Stop").apply { isEnabled = false }

    private val processManager = CliProcessManager(project)

    init {
        setupUI()
        setupListeners()
    }

    private fun setupUI() {
        // Messages area with scroll
        val scrollPane = JBScrollPane(messagesArea)
        add(scrollPane, BorderLayout.CENTER)

        // Input panel at bottom
        val inputPanel = JPanel(BorderLayout())
        inputPanel.add(JBScrollPane(inputField), BorderLayout.CENTER)

        val buttonPanel = JPanel()
        buttonPanel.add(sendButton)
        buttonPanel.add(stopButton)
        inputPanel.add(buttonPanel, BorderLayout.EAST)

        add(inputPanel, BorderLayout.SOUTH)

        // Status bar
        val statusLabel = JLabel("Ready")
        add(statusLabel, BorderLayout.NORTH)
    }

    private fun setupListeners() {
        sendButton.addActionListener { sendMessage() }

        stopButton.addActionListener {
            processManager.stop()
            stopButton.isEnabled = false
        }

        inputField.addKeyListener(object : KeyAdapter() {
            override fun keyPressed(e: KeyEvent) {
                if (e.keyCode == KeyEvent.VK_ENTER && e.isControlDown) {
                    sendMessage()
                    e.consume()
                }
            }
        })
    }

    private fun sendMessage() {
        val text = inputField.text.trim()
        if (text.isEmpty()) return

        // Check if already processing
        if (processManager.isRunning()) {
            appendMessage("System", "A request is already in progress...")
            return
        }

        appendMessage("You", text)
        inputField.text = ""
        stopButton.isEnabled = true

        // Send message with output callback
        processManager.sendMessage(text) { output ->
            SwingUtilities.invokeLater {
                // Append CLI output directly (filter out ANSI control chars)
                val cleanOutput = output.replace(Regex("\\x1B\\[[0-9;]*[a-zA-Z]"), "")
                if (cleanOutput.isNotBlank()) {
                    messagesArea.append(cleanOutput)
                    messagesArea.caretPosition = messagesArea.document.length
                }
            }
        }
    }

    private fun appendMessage(sender: String, message: String) {
        messagesArea.append("[$sender]\n$message\n\n")
        messagesArea.caretPosition = messagesArea.document.length
    }

    fun dispose() {
        processManager.stop()
    }
}
