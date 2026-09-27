using System;
using System.Diagnostics;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;

namespace DivAcerManagerMax;

/// <summary>
///     Shows the daemon's recent log, which it writes to the systemd journal
/// </summary>
/// <remarks>
///     Reading a system service's journal needs membership of a group such as
///     wheel, adm or systemd-journal; journalctl says so when it is missing.
/// </remarks>
public class DaemonLogWindow : Window
{
    private const string Unit = "damx-daemon.service";
    private const int Lines = 1000;

    private readonly TextBox _log;

    public DaemonLogWindow()
    {
        Title = "DAMX Daemon Log";
        Width = 900;
        Height = 600;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;

        var refresh = new Button { Content = "Refresh", Margin = new Avalonia.Thickness(8) };
        refresh.Click += async (_, _) => await LoadAsync();

        var header = new StackPanel { Orientation = Orientation.Horizontal };
        header.Children.Add(refresh);
        header.Children.Add(new TextBlock
        {
            Text = $"journalctl -u {Unit} -n {Lines}",
            VerticalAlignment = VerticalAlignment.Center,
            FontFamily = new FontFamily("monospace")
        });

        _log = new TextBox
        {
            IsReadOnly = true,
            AcceptsReturn = true,
            TextWrapping = TextWrapping.NoWrap,
            FontFamily = new FontFamily("monospace")
        };

        var panel = new DockPanel();
        DockPanel.SetDock(header, Dock.Top);
        panel.Children.Add(header);
        panel.Children.Add(_log);
        Content = panel;

        Opened += async (_, _) => await LoadAsync();
    }

    private async Task LoadAsync()
    {
        _log.Text = await ReadJournalAsync();
        _log.CaretIndex = _log.Text.Length;
    }

    private static async Task<string> ReadJournalAsync()
    {
        var startInfo = new ProcessStartInfo("journalctl")
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        foreach (var argument in new[] { "-u", Unit, "-n", Lines.ToString(), "--no-pager", "-o", "short-iso" })
            startInfo.ArgumentList.Add(argument);

        try
        {
            using var process = Process.Start(startInfo)!;
            var output = process.StandardOutput.ReadToEndAsync();
            var errors = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            return (await errors).Length > 0 ? $"{await errors}\n{await output}" : await output;
        }
        catch (Exception ex)
        {
            return $"Could not run journalctl: {ex.Message}";
        }
    }
}
