package com.ccb.ide.config

import com.intellij.openapi.options.Configurable
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JSpinner
import javax.swing.SpinnerNumberModel

class CcbSettingsConfigurable : Configurable {

    private var panel: JPanel? = null
    private var cliPathField: JBTextField? = null
    private var providerField: JBTextField? = null
    private var autoInjectCheckbox: JBCheckBox? = null
    private var notificationsCheckbox: JBCheckBox? = null
    private var autoOpenCheckbox: JBCheckBox? = null
    private var fontSizeSpinner: JSpinner? = null

    override fun getDisplayName(): String = "Claude Code Bridge"

    override fun createComponent(): JComponent {
        cliPathField = JBTextField()
        providerField = JBTextField()
        autoInjectCheckbox = JBCheckBox("Auto-inject selected code as context")
        notificationsCheckbox = JBCheckBox("Show notifications")
        autoOpenCheckbox = JBCheckBox("Auto-open on project startup")
        fontSizeSpinner = JSpinner(SpinnerNumberModel(14, 8, 32, 1))

        panel = FormBuilder.createFormBuilder()
            .addLabeledComponent(JBLabel("CLI Path (leave empty for 'claude'):"), cliPathField!!, 1, false)
            .addLabeledComponent(JBLabel("Default Provider:"), providerField!!, 1, false)
            .addLabeledComponent(JBLabel("Terminal Font Size:"), fontSizeSpinner!!, 1, false)
            .addComponent(autoInjectCheckbox!!, 1)
            .addComponent(notificationsCheckbox!!, 1)
            .addComponent(autoOpenCheckbox!!, 1)
            .addComponentFillVertically(JPanel(), 0)
            .panel

        return panel!!
    }

    override fun isModified(): Boolean {
        val settings = CcbSettings.getInstance()
        return cliPathField?.text != settings.cliPath ||
               providerField?.text != settings.defaultProvider ||
               autoInjectCheckbox?.isSelected != settings.autoInjectContext ||
               notificationsCheckbox?.isSelected != settings.showNotifications ||
               autoOpenCheckbox?.isSelected != settings.autoOpenOnStartup ||
               (fontSizeSpinner?.value as? Int) != settings.terminalFontSize
    }

    override fun apply() {
        val settings = CcbSettings.getInstance()
        settings.cliPath = cliPathField?.text ?: ""
        settings.defaultProvider = providerField?.text ?: "claude"
        settings.autoInjectContext = autoInjectCheckbox?.isSelected ?: true
        settings.showNotifications = notificationsCheckbox?.isSelected ?: true
        settings.autoOpenOnStartup = autoOpenCheckbox?.isSelected ?: false
        settings.terminalFontSize = (fontSizeSpinner?.value as? Int) ?: 14
    }

    override fun reset() {
        val settings = CcbSettings.getInstance()
        cliPathField?.text = settings.cliPath
        providerField?.text = settings.defaultProvider
        autoInjectCheckbox?.isSelected = settings.autoInjectContext
        notificationsCheckbox?.isSelected = settings.showNotifications
        autoOpenCheckbox?.isSelected = settings.autoOpenOnStartup
        fontSizeSpinner?.value = settings.terminalFontSize
    }

    override fun disposeUIResources() {
        panel = null
        cliPathField = null
        providerField = null
        autoInjectCheckbox = null
        notificationsCheckbox = null
        autoOpenCheckbox = null
        fontSizeSpinner = null
    }
}
