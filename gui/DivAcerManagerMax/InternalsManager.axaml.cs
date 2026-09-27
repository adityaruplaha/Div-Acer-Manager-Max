using System;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Interactivity;
using MsBox.Avalonia;

namespace DivAcerManagerMax;

public partial class InternalsManager : Window
{
    private readonly bool _isInitializing;
    private readonly MainWindow _mainWindow;
    private bool _isProcessingParameterChange;
    private int _lastSelectedIndex = -1;

    public InternalsManager(MainWindow mainWindow)
    {
        _isInitializing = true;
        InitializeComponent();
        _mainWindow = mainWindow;
        InitializeUiComponents();
        _isInitializing = false;
    }

    public void InitializeUiComponents()
    {
        DevModeToggleSwitch.IsChecked = MainWindow.AppState.DevMode;

        ForceParameterPermanentlyComboBox.SelectedIndex = _mainWindow._settings.ModprobeParameter switch
        {
            "predator_v4" => 1,
            "nitro_v4" => 2,
            "enable_all" => 3,
            _ => 0 // Default to "No Parameter" for empty string or unknown values
        };

        // Store the initial selection to prevent unnecessary triggers
        _lastSelectedIndex = ForceParameterPermanentlyComboBox.SelectedIndex;
    }

    private void DevModeSwitch_OnClick(object? sender, RoutedEventArgs e)
    {
        _mainWindow.EnableDevMode(DevModeToggleSwitch.IsChecked == true);
    }

    public void ReinitializeDamxGUI()
    {
        _mainWindow.InitializeAsync();
    }

    private void DaemonLogsButton_OnClick(object? sender, RoutedEventArgs e)
    {
        new DaemonLogWindow().Show(this);
    }

    private async void RestartSuiteButton_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunDaemonCommandAsync("restart_drivers_and_daemon", "Restarting Suite",
            "Restarting Suite and refreshing GUI, please wait");
    }

    private async void ForcePredatorButton_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunDaemonCommandAsync("force_predator_model", "Forcing Predator Model",
            "Restarting Drivers with predator_v4 parameter with daemon and refreshing GUI, please wait");
    }

    private async void ForceNitroButton_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunDaemonCommandAsync("force_nitro_model", "Forcing Nitro Model",
            "Restarting Drivers with nitro_v4 parameter with daemon and refreshing GUI, please wait");
    }

    private async void RestartDaemon_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunDaemonCommandAsync("restart_daemon", "Restarting Daemon",
            "Restarting Daemon refreshing GUI, please wait");
    }

    /// <summary>
    ///     Run a command that reloads the driver or restarts the daemon, and report how it went
    /// </summary>
    /// <remarks>
    ///     The daemon answers once polkit has asked for a password, where it
    ///     needs one, and the command has run; it restarts itself after
    ///     answering, so the GUI is refreshed once it is back.
    /// </remarks>
    private async Task RunDaemonCommandAsync(string command, string title, string message)
    {
        if (!_mainWindow._client.IsConnected)
        {
            await ShowMessagebox("Error", "Daemon is not connected");
            return;
        }

        try
        {
            using var response = await _mainWindow._client.SendCommandAsync(command);
            var root = response.RootElement;
            if (!root.GetProperty("success").GetBoolean())
            {
                var error = root.TryGetProperty("error", out var e) ? e.GetString() : "unknown error";
                await ShowMessagebox("Error", $"{title} failed: {error}");
                return;
            }

            await Task.Delay(1000);
            ReinitializeDamxGUI();
            await ShowMessagebox(title, message);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error running {command}: {ex.Message}");
            await ShowMessagebox("Error", $"{title} failed: {ex.Message}");
        }
    }

    private async Task ShowMessagebox(string title, string message)
    {
        try
        {
            var box = MessageBoxManager.GetMessageBoxStandard(title, message);
            await box.ShowWindowDialogAsync(this);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error showing messagebox: {ex.Message}");
        }
    }

    private async void ForceEnableAll_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunDaemonCommandAsync("force_enable_all", "Forcing All Features",
            "Initializing Drivers with enable_all parameter. Restarting daemon and refreshing GUI, please wait");
    }

    private async void ForceParameterPermanently_OnSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (_isInitializing) return;
        // Prevent re-entrancy
        if (_isProcessingParameterChange) return;

        var comboBox = sender as ComboBox;
        if (comboBox == null || comboBox.SelectedIndex == -1) return;

        // Check if this is a real change
        if (comboBox.SelectedIndex == _lastSelectedIndex) return;
        _lastSelectedIndex = comboBox.SelectedIndex;

        _isProcessingParameterChange = true;

        try
        {
            switch (comboBox.SelectedIndex)
            {
                case 0:
                    await SendParameterCommand("remove_modprobe_parameter", "Removing Modprobe Parameter");
                    break;
                case 1:
                    await SendParameterCommand("set_modprobe_parameter_predator", "Setting Predator Parameter");
                    break;
                case 2:
                    await SendParameterCommand("set_modprobe_parameter_nitro", "Setting Nitro Parameter");
                    break;
                case 3:
                    await SendParameterCommand("set_modprobe_parameter_enable_all", "Setting Enable All Parameter");
                    break;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error in ForceParameterPermanently_OnSelectionChanged: {ex.Message}");
            await ShowMessagebox("Error", $"Failed to change parameter: {ex.Message}");
        }
        finally
        {
            _isProcessingParameterChange = false;
        }
    }

    private async Task SendParameterCommand(string command, string actionName)
    {
        // The daemon reloads the driver with the new parameter and restarts itself
        await RunDaemonCommandAsync(command, actionName,
            $"{actionName}: reloading the driver and restarting the daemon, then refreshing the GUI");
    }

    // Add this method to help with debugging
    public async void RefreshModprobeParameterState()
    {
        try
        {
            if (_mainWindow._client.IsConnected)
                // You'll need to add a "get_modprobe_parameter" command to your daemon
                // For now, just log that we're checking
                Console.WriteLine("Checking modprobe parameter state...");
            // If you add the command, you can use it like this:
            // await _mainWindow._client.SendCommandWithResponseAsync("get_modprobe_parameter");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error refreshing parameter state: {ex.Message}");
        }
    }
}