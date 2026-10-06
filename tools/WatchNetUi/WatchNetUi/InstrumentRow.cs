using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace WatchNetUi;

public sealed class InstrumentRow : INotifyPropertyChanged
{
    private string _status = "стоп";
    private DateTime? _lastNetUpdate;
    private DateTime? _barsM1Write;
    private string _etaText = "—";
    private string _lastText = "—";
    private string _ageText = "—";
    private int? _pid;
    private bool _isRunning;
    private string _detail = "";

    public required string Sec { get; init; }
    public required string ClassCode { get; init; }
    public string Key => $"{Sec}:{ClassCode}";

    public string Status
    {
        get => _status;
        set => Set(ref _status, value);
    }

    public DateTime? LastNetUpdate
    {
        get => _lastNetUpdate;
        set
        {
            if (Set(ref _lastNetUpdate, value))
                LastText = value?.ToString("HH:mm:ss") ?? "нет CSV";
        }
    }

    public DateTime? BarsM1Write
    {
        get => _barsM1Write;
        set => Set(ref _barsM1Write, value);
    }

    public string LastText
    {
        get => _lastText;
        private set => Set(ref _lastText, value);
    }

    public string AgeText
    {
        get => _ageText;
        set => Set(ref _ageText, value);
    }

    public string EtaText
    {
        get => _etaText;
        set => Set(ref _etaText, value);
    }

    public int? Pid
    {
        get => _pid;
        set => Set(ref _pid, value);
    }

    public bool IsRunning
    {
        get => _isRunning;
        set => Set(ref _isRunning, value);
    }

    public string Detail
    {
        get => _detail;
        set => Set(ref _detail, value);
    }

    public string WorkerLabel
    {
        get => _workerLabel;
        set => Set(ref _workerLabel, value);
    }

    /// <summary>Measured seconds between consecutive net CSV writes while running.</summary>
    public double CycleSeconds { get; set; } = 90;

    private string _workerLabel = "—";

    public event PropertyChangedEventHandler? PropertyChanged;

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (Equals(field, value)) return false;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
        return true;
    }
}
