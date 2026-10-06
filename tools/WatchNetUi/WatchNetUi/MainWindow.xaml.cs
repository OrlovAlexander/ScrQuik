using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Threading;

namespace WatchNetUi;

public partial class MainWindow : Window
{
    private readonly ObservableCollection<InstrumentRow> _rows = new();
    private readonly WatchNetSupervisor _supervisor;
    private readonly DispatcherTimer _timer;
    private readonly Dictionary<string, DateTime?> _prevNet = new(StringComparer.OrdinalIgnoreCase);
    private int _logLines;

    public MainWindow()
    {
        InitializeComponent();
        Grid.ItemsSource = _rows;
        _supervisor = new WatchNetSupervisor();
        _supervisor.Log += OnWorkerLog;

        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _timer.Tick += (_, _) => RefreshStatuses();
        _timer.Start();

        Loaded += (_, _) =>
        {
            AppendLog($"repo={_supervisor.RepoRoot}");
            AppendLog($"python={_supervisor.PythonExe}");
            AppendLog($"лимит воркеров={WatchNetSupervisor.JobsCap} (больше — thrash, CSV почти не двигаются)");
            ReloadInstruments();
        };
    }

    private void ReloadInstruments()
    {
        var states = _rows.ToDictionary(r => r.Key, r => r, StringComparer.OrdinalIgnoreCase);
        _rows.Clear();
        foreach (var (sec, cls) in InstrumentScanner.ListInstruments())
        {
            if (states.TryGetValue($"{sec}:{cls}", out var old))
            {
                _rows.Add(old);
                continue;
            }
            _rows.Add(new InstrumentRow { Sec = sec, ClassCode = cls });
        }

        AppendLog($"инструментов: {_rows.Count}");
        RefreshStatuses();
    }

    private void RefreshStatuses()
    {
        var now = DateTime.Now;
        var covered = 0;
        foreach (var row in _rows)
        {
            var net = InstrumentScanner.BestNetWrite(row.Sec, row.ClassCode);
            var bars = InstrumentScanner.FileWriteUtc(InstrumentScanner.BarsM1Path(row.Sec, row.ClassCode));
            row.BarsM1Write = bars;

            if (_prevNet.TryGetValue(row.Key, out var prev) && net != null && prev != null && net > prev)
            {
                var cycle = (net.Value - prev.Value).TotalSeconds;
                if (cycle is > 20 and < 900)
                    row.CycleSeconds = 0.7 * row.CycleSeconds + 0.3 * cycle;
            }
            _prevNet[row.Key] = net;
            row.LastNetUpdate = net;

            var isRun = _supervisor.IsInstrumentCovered(row.Key);
            row.IsRunning = isRun;
            row.Pid = _supervisor.PidForInstrument(row.Key);
            var wid = _supervisor.WorkerIdForInstrument(row.Key);
            row.WorkerLabel = wid ?? "—";
            if (isRun) covered++;

            row.Status = isRun ? "run" : "стоп";

            var shardSize = wid != null ? _supervisor.InstrumentsInWorker(wid).Count : 1;
            var busySec = wid != null ? _supervisor.BusySecForWorker(wid) : null;
            var computingThis = busySec != null
                && busySec.Equals(row.Sec, StringComparison.OrdinalIgnoreCase);

            if (net == null)
            {
                row.AgeText = "—";
                if (!isRun)
                {
                    row.EtaText = "—";
                    row.Detail = "";
                }
                else if (computingThis)
                {
                    row.EtaText = "считает сейчас";
                    row.Detail = $"первая выгрузка {row.Sec} (~1–2 мин)";
                }
                else if (busySec != null)
                {
                    row.EtaText = "в очереди";
                    row.Detail = $"шард считает {busySec}; потом {row.Sec}";
                }
                else
                {
                    row.EtaText = "ждёт первую выгрузку";
                    row.Detail = shardSize > 1 ? $"шард {shardSize} тик." : "process up, CSV ещё нет";
                }
                continue;
            }

            var age = now - net.Value;
            row.AgeText = FormatSpan(age);

            var barsNewer = bars != null && bars > net.Value.AddSeconds(2);
            if (isRun && barsNewer && bars is not null)
            {
                var wait = now - bars.Value;
                if (computingThis)
                {
                    row.EtaText = "считает сейчас";
                    row.Detail =
                        $"export {row.Sec}; bars новее на {FormatSpan(bars.Value - net.Value)}; уже {FormatSpan(wait)}";
                }
                else if (busySec != null)
                {
                    row.EtaText = "в очереди";
                    row.Detail =
                        $"шард считает {busySec}; {row.Sec} ждёт {FormatSpan(wait)}"
                        + (shardSize > 1 ? $"; fair среди {shardSize}" : "");
                }
                else
                {
                    row.EtaText = "в очереди/счёт";
                    row.Detail =
                        $"bars новее на {FormatSpan(bars.Value - net.Value)}; ждёт/считает {FormatSpan(wait)}"
                        + (shardSize > 1 ? $"; fair среди {shardSize}" : "");
                }
            }
            else
            {
                // In a shard of K with 1 export ~80s, full round ≈ K * cycle.
                var unit = Math.Max(30, row.CycleSeconds);
                var cycle = isRun && shardSize > 1 ? unit * shardSize : unit;
                var due = net.Value.AddSeconds(cycle);
                var left = due - now;
                if (left.TotalSeconds > 0)
                {
                    row.EtaText = FormatSpan(left);
                    row.Detail = isRun
                        ? $"круг ≈ {cycle:0}s" + (shardSize > 1 ? $" ({shardSize}×{unit:0}s)" : "")
                        : "не в пуле";
                }
                else
                {
                    row.EtaText = isRun ? "ожидает тик" : "—";
                    row.Detail = isRun
                        ? $"просрочено {FormatSpan(now - due)}; круг ≈ {cycle:0}s"
                        : "";
                }
            }
        }

        TxtSummary.Text =
            $"покрыто {covered}/{_rows.Count}  ·  воркеров {_supervisor.WorkerCount}/{WatchNetSupervisor.JobsCap}  ·  {now:HH:mm:ss}";
    }

    private static string FormatSpan(TimeSpan t)
    {
        if (t.TotalSeconds < 0) t = -t;
        if (t.TotalHours >= 1) return $"{(int)t.TotalHours}ч {t.Minutes:D2}м";
        if (t.TotalMinutes >= 1) return $"{(int)t.TotalMinutes}м {t.Seconds:D2}с";
        return $"{(int)t.TotalSeconds}с";
    }

    private int ReadJobs(out int requested)
    {
        if (!int.TryParse(TxtMaxParallel.Text.Trim(), out var max) || max < 1)
            max = WatchNetSupervisor.JobsCap;
        requested = max;
        var clamped = WatchNetSupervisor.ClampJobs(max);
        if (clamped != max)
            TxtMaxParallel.Text = clamped.ToString();
        return clamped;
    }

    private void BtnRefresh_Click(object sender, RoutedEventArgs e) => ReloadInstruments();

    private void BtnStartSelected_Click(object sender, RoutedEventArgs e)
    {
        var selected = Grid.SelectedItems.Cast<InstrumentRow>().ToList();
        if (selected.Count == 0)
        {
            AppendLog("выберите строки");
            return;
        }

        var jobs = ReadJobs(out var requested);
        if (requested != jobs)
            AppendLog($"запрошено {requested} → обрезано до {jobs} (иначе thrash, CSV стоят)");
        var list = selected.Select(r => (r.Sec, r.ClassCode)).ToList();
        // Selected few → dedicated; many → shard pool over selection only.
        if (selected.Count <= jobs)
        {
            var n = _supervisor.StartDedicated(list, jobs);
            AppendLog($"старт выделенных: {n} (лимит воркеров {jobs})");
        }
        else
        {
            var n = _supervisor.StartPool(list, jobs);
            AppendLog($"старт пула по выбранным: {n} воркеров на {list.Count} тикеров");
        }
        RefreshStatuses();
    }

    private void BtnStartAll_Click(object sender, RoutedEventArgs e)
    {
        var jobs = ReadJobs(out var requested);
        if (requested != jobs)
            AppendLog($"запрошено {requested} → обрезано до {jobs} (иначе thrash, CSV стоят)");
        var list = _rows.Select(r => (r.Sec, r.ClassCode)).ToList();
        if (list.Count == 0)
        {
            AppendLog("список пуст");
            return;
        }

        var n = _supervisor.StartPool(list, jobs);
        var per = (list.Count + n - 1) / n;
        AppendLog($"пул: {n} воркеров × ~{per} тикеров (все {list.Count}). Fair-очередь внутри шарда. 1 export ≈ 1–2 мин.");
        RefreshStatuses();
    }

    private void BtnStopSelected_Click(object sender, RoutedEventArgs e)
    {
        var workers = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in Grid.SelectedItems.Cast<InstrumentRow>())
        {
            var wid = _supervisor.WorkerIdForInstrument(row.Key);
            if (wid != null) workers.Add(wid);
        }
        foreach (var wid in workers)
            _supervisor.StopWorker(wid);
        AppendLog($"остановлено воркеров: {workers.Count}");
        RefreshStatuses();
    }

    private void BtnStopAll_Click(object sender, RoutedEventArgs e)
    {
        _supervisor.StopAll();
        foreach (var row in _rows)
        {
            row.IsRunning = false;
            row.Pid = null;
            row.Status = "стоп";
            row.WorkerLabel = "—";
        }
        AppendLog("все остановлены");
        RefreshStatuses();
    }

    private void OnWorkerLog(string key, string message)
    {
        // BeginInvoke: sync Invoke from 20 stdout readers can stall the pipe and freeze exports.
        Dispatcher.BeginInvoke(() => AppendLog($"{key}  {message}"));
    }

    private void AppendLog(string line)
    {
        _logLines++;
        if (_logLines > 500)
        {
            TxtLog.Clear();
            _logLines = 0;
        }
        TxtLog.AppendText($"[{DateTime.Now:HH:mm:ss}] {line}{Environment.NewLine}");
        TxtLog.ScrollToEnd();
    }

    private void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _timer.Stop();
        _supervisor.Dispose();
    }
}
