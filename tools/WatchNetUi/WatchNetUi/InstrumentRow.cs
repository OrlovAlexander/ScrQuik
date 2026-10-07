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
    private string _barsAgeText = "—";
    private string _barsStatus = "—";
    private string _marksAgeText = "—";
    private string _marksStatus = "—";
    private string _lastPriceText = "—";
    private string _volTodayText = "—";
    private string _valTodayText = "—";
    private double _volTodayValue = -1;
    private double _valTodayValue = -1;
    private double _lastPriceValue = -1;

    public required string Sec { get; init; }
    public required string ClassCode { get; init; }
    public string Key => $"{Sec}:{ClassCode}";

    /// <summary>0 = SPBFUT (always first), 1 = rest.</summary>
    public int ClassSortKey =>
        ClassCode.Equals("SPBFUT", StringComparison.OrdinalIgnoreCase) ? 0 : 1;

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

    public string BarsAgeText
    {
        get => _barsAgeText;
        set => Set(ref _barsAgeText, value);
    }

    public string BarsStatus
    {
        get => _barsStatus;
        set => Set(ref _barsStatus, value);
    }

    public string MarksAgeText
    {
        get => _marksAgeText;
        set => Set(ref _marksAgeText, value);
    }

    public string MarksStatus
    {
        get => _marksStatus;
        set => Set(ref _marksStatus, value);
    }

    /// <summary>LAST from SecDump (QUIK).</summary>
    public string LastPriceText
    {
        get => _lastPriceText;
        private set => Set(ref _lastPriceText, value);
    }

    /// <summary>VOLTODAY from SecDump.</summary>
    public string VolTodayText
    {
        get => _volTodayText;
        private set => Set(ref _volTodayText, value);
    }

    /// <summary>VALTODAY from SecDump.</summary>
    public string ValTodayText
    {
        get => _valTodayText;
        private set => Set(ref _valTodayText, value);
    }

    /// <summary>Raw VOLTODAY for numeric sort (−1 if missing).</summary>
    public double VolTodayValue
    {
        get => _volTodayValue;
        private set => Set(ref _volTodayValue, value);
    }

    /// <summary>Raw VALTODAY for numeric sort (−1 if missing).</summary>
    public double ValTodayValue
    {
        get => _valTodayValue;
        private set => Set(ref _valTodayValue, value);
    }

    public double LastPriceValue
    {
        get => _lastPriceValue;
        private set => Set(ref _lastPriceValue, value);
    }

    public void SetQuote(double? last, double? volToday, double? valToday)
    {
        LastPriceText = QuikSecDump.FormatLast(last);
        VolTodayText = QuikSecDump.FormatVol(volToday);
        ValTodayText = QuikSecDump.FormatVal(valToday);
        LastPriceValue = last ?? -1;
        VolTodayValue = volToday ?? -1;
        ValTodayValue = valToday ?? -1;
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
