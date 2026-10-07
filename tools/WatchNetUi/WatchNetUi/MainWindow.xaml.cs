using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Media;
using System.Windows.Threading;

namespace WatchNetUi;

public partial class MainWindow : Window
{
    private readonly ObservableCollection<InstrumentRow> _rows = new();
    private readonly WatchNetSupervisor _supervisor;
    private readonly MarksWatchSupervisor _marks;
    private readonly DispatcherTimer _timer;
    private readonly Dictionary<string, DateTime?> _prevNet = new(StringComparer.OrdinalIgnoreCase);
    private int _logLines;
    private bool _marksOnceBusy;
    private string _sortPath = nameof(InstrumentRow.ValTodayValue);
    private ListSortDirection _sortDir = ListSortDirection.Descending;

    public MainWindow()
    {
        InitializeComponent();
        Grid.ItemsSource = _rows;
        ConfigureLiveSort();
        _supervisor = new WatchNetSupervisor();
        _supervisor.Log += OnWorkerLog;
        _marks = new MarksWatchSupervisor(_supervisor.RepoRoot, _supervisor.PythonExe);
        _marks.Log += msg => Dispatcher.BeginInvoke(() => AppendLog("marks  " + msg));

        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _timer.Tick += (_, _) => RefreshStatuses();
        _timer.Start();

        Loaded += (_, _) =>
        {
            AppendLog($"repo={_supervisor.RepoRoot}");
            AppendLog($"python={_supervisor.PythonExe}");
            AppendLog($"лимит воркеров сети={WatchNetSupervisor.JobsCap}");
            var foreign = MarksWatchSupervisor.FindForeignMarksWatchPids();
            if (foreign.Count > 0)
                AppendLog($"уже есть --watch pid={string.Join(",", foreign)} (можно «Метки: стоп»)");
            ReloadInstruments();
        };
    }

    private void ConfigureLiveSort()
    {
        var view = CollectionViewSource.GetDefaultView(_rows);
        if (view is ICollectionViewLiveShaping live)
        {
            live.IsLiveSorting = true;
            live.LiveSortingProperties.Clear();
            live.LiveSortingProperties.Add(nameof(InstrumentRow.ClassSortKey));
            live.LiveSortingProperties.Add(nameof(InstrumentRow.VolTodayValue));
            live.LiveSortingProperties.Add(nameof(InstrumentRow.ValTodayValue));
            live.LiveSortingProperties.Add(nameof(InstrumentRow.LastPriceValue));
        }
        ApplyGridSort(nameof(InstrumentRow.ValTodayValue), ListSortDirection.Descending, syncHeaders: true);
    }

    private void ApplyGridSort(string path, ListSortDirection dir, bool syncHeaders)
    {
        _sortPath = path;
        _sortDir = dir;
        var view = CollectionViewSource.GetDefaultView(_rows);
        using (view.DeferRefresh())
        {
            view.SortDescriptions.Clear();
            // SPBFUT always first, then numeric/text column (тыс/млн/млрд — по сырому числу).
            view.SortDescriptions.Add(
                new SortDescription(nameof(InstrumentRow.ClassSortKey), ListSortDirection.Ascending));
            if (!string.Equals(path, nameof(InstrumentRow.ClassSortKey), StringComparison.Ordinal))
                view.SortDescriptions.Add(new SortDescription(path, dir));
        }

        if (!syncHeaders) return;
        foreach (var col in Grid.Columns)
        {
            if (col.SortMemberPath == path)
                col.SortDirection = dir;
            else
                col.SortDirection = null;
        }
    }

    private void Grid_Sorting(object sender, DataGridSortingEventArgs e)
    {
        e.Handled = true;
        var path = e.Column.SortMemberPath;
        if (string.IsNullOrEmpty(path)) return;

        var dir = ListSortDirection.Ascending;
        if (e.Column.SortDirection == ListSortDirection.Ascending)
            dir = ListSortDirection.Descending;
        else if (path is nameof(InstrumentRow.VolTodayValue)
                 or nameof(InstrumentRow.ValTodayValue)
                 or nameof(InstrumentRow.LastPriceValue))
            dir = ListSortDirection.Descending; // first click on volume/turnover: largest first

        ApplyGridSort(path, dir, syncHeaders: true);
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
        var snap = BarsHealth.Build(_rows.Select(r => (r.Sec, r.ClassCode)), now);
        TxtBarsSummary.Text = snap.Summary;
        TxtBarsSummary.Foreground = snap is { QuikRunning: true, BarsDirOk: true, StaleM1: 0, BehindM10: 0 }
            ? Brushes.LightGreen
            : snap.BehindM10 > 0 || snap.StaleM1 > 0 || !snap.QuikRunning
                ? Brushes.Orange
                : Brushes.LightSkyBlue;

        var marksFresh = 0;
        var marksStale = 0;
        var marksMissing = 0;

        QuikSecDump.LoadCached();

        foreach (var row in _rows)
        {
            var quote = QuikSecDump.Find(row.Sec, row.ClassCode);
            row.SetQuote(quote?.Last, quote?.VolToday, quote?.ValToday);

            var net = InstrumentScanner.BestNetWrite(row.Sec, row.ClassCode);
            var barsInfo = BarsHealth.ForInstrument(row.Sec, row.ClassCode, now);
            var bars = barsInfo.M1;
            row.BarsM1Write = bars;
            row.BarsAgeText = barsInfo.AgeText;
            row.BarsStatus = barsInfo.Status;

            var marks = InstrumentScanner.BestMarksWrite(row.Sec, row.ClassCode);
            if (marks == null)
            {
                row.MarksAgeText = "—";
                row.MarksStatus = "нет";
                marksMissing++;
            }
            else
            {
                var mage = now - marks.Value;
                row.MarksAgeText = FormatSpan(mage);
                if (mage.TotalMinutes < 3)
                {
                    row.MarksStatus = "ok";
                    marksFresh++;
                }
                else if (mage.TotalMinutes < 15)
                {
                    row.MarksStatus = "тихо";
                }
                else
                {
                    row.MarksStatus = "stale";
                    marksStale++;
                }
            }

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

        var marksPid = _marks.Pid;
        var foreign = MarksWatchSupervisor.FindForeignMarksWatchPids();
        var marksRun = _marks.IsRunning || foreign.Count > 0;
        var shownPid = marksPid ?? (foreign.Count > 0 ? foreign[0] : (int?)null);
        TxtMarksSummary.Text = marksRun
            ? $"marks: watch pid={shownPid} · CSV свежих(<3м) {marksFresh}/{_rows.Count} · stale {marksStale} · нет {marksMissing}"
            : $"marks: watch стоп · CSV свежих(<3м) {marksFresh}/{_rows.Count} · stale {marksStale} · нет {marksMissing}";
        TxtMarksSummary.Foreground = marksRun ? Brushes.LightGreen : Brushes.Orange;

        TxtSummary.Text =
            $"сеть {covered}/{_rows.Count} · w {_supervisor.WorkerCount}/{WatchNetSupervisor.JobsCap} · {now:HH:mm:ss}";
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

    private void BtnAddInstrument_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new AddInstrumentWindow { Owner = this };
        if (dlg.ShowDialog() != true) return;
        try
        {
            var report = InstrumentLifecycle.AddToSecList(dlg.SecCode, dlg.ClassCode);
            AppendLog($"add {report.Sec}:{report.ClassCode}  {report.Note}");
            MessageBox.Show(
                this,
                report.Note,
                "Инструмент в sec_list",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            ReloadInstruments();
        }
        catch (Exception ex)
        {
            AppendLog("add failed: " + ex.Message);
            MessageBox.Show(this, ex.Message, "Ошибка", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private void BtnRemoveInstrument_Click(object sender, RoutedEventArgs e)
    {
        var selected = Grid.SelectedItems.Cast<InstrumentRow>().ToList();
        if (selected.Count == 0)
        {
            AppendLog("выберите строки для удаления");
            return;
        }

        var names = string.Join(", ", selected.Select(r => r.Key).Take(12));
        if (selected.Count > 12) names += "…";
        var ask = MessageBox.Show(
            this,
            $"Удалить {selected.Count} инструмент(ов) из sec_list и стереть CSV bars/marks/net?\n\n{names}\n\n"
            + "Сеть по ним будет остановлена. barsSaver в QUIK нужно перезапустить.",
            "Удалить инструменты",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (ask != MessageBoxResult.Yes) return;

        foreach (var row in selected)
        {
            try
            {
                _supervisor.StopInstrument(row.Key);
                var report = InstrumentLifecycle.RemoveEverywhere(row.Sec, row.ClassCode);
                AppendLog($"remove {report.Sec}:{report.ClassCode}  {report.Note}");
                foreach (var f in report.DeletedFiles.Take(8))
                    AppendLog("  del " + f);
                if (report.DeletedFiles.Count > 8)
                    AppendLog($"  … ещё {report.DeletedFiles.Count - 8} файлов");
            }
            catch (Exception ex)
            {
                AppendLog($"remove {row.Key} failed: {ex.Message}");
            }
        }

        ReloadInstruments();
    }

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
        if (selected.Count <= jobs)
        {
            var n = _supervisor.StartDedicated(list, jobs);
            AppendLog($"сеть старт выделенных: {n} (лимит {jobs})");
        }
        else
        {
            var n = _supervisor.StartPool(list, jobs);
            AppendLog($"сеть пул по выбранным: {n} воркеров на {list.Count}");
        }
        RefreshStatuses();
    }

    private void BtnStartAll_Click(object sender, RoutedEventArgs e)
    {
        var jobs = ReadJobs(out var requested);
        if (requested != jobs)
            AppendLog($"запрошено {requested} → обрезано до {jobs}");
        var list = _rows.Select(r => (r.Sec, r.ClassCode)).ToList();
        if (list.Count == 0)
        {
            AppendLog("список пуст");
            return;
        }

        var n = _supervisor.StartPool(list, jobs);
        var per = (list.Count + n - 1) / n;
        AppendLog($"сеть пул: {n} × ~{per} тикеров (все {list.Count})");
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
        AppendLog($"сеть остановлено воркеров: {workers.Count}");
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
        AppendLog("сеть: все остановлены");
        RefreshStatuses();
    }

    private void BtnMarksWatch_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            if (_marks.IsRunning)
            {
                AppendLog($"marks watch уже pid={_marks.Pid}");
                return;
            }
            _marks.StartWatch();
            RefreshStatuses();
        }
        catch (Exception ex)
        {
            AppendLog("marks watch failed: " + ex.Message);
        }
    }

    private void BtnMarksStop_Click(object sender, RoutedEventArgs e)
    {
        _marks.CancelOneShot();
        _marks.StopWatch();
        RefreshStatuses();
    }

    private async void BtnMarksOnce_Click(object sender, RoutedEventArgs e)
    {
        if (_marksOnceBusy)
        {
            AppendLog("marks разово уже идёт");
            return;
        }

        var selected = Grid.SelectedItems.Cast<InstrumentRow>().ToList();
        if (selected.Count == 0)
        {
            AppendLog("выберите строки для разового --marks");
            return;
        }

        _marksOnceBusy = true;
        BtnMarksOnce.IsEnabled = false;
        try
        {
            var list = selected.Select(r => (r.Sec, r.ClassCode)).ToList();
            await _marks.ExportSelectedAsync(list).ConfigureAwait(true);
        }
        catch (OperationCanceledException)
        {
            AppendLog("marks разово отменено");
        }
        catch (Exception ex)
        {
            AppendLog("marks разово failed: " + ex.Message);
        }
        finally
        {
            _marksOnceBusy = false;
            BtnMarksOnce.IsEnabled = true;
            RefreshStatuses();
        }
    }

    private void OnWorkerLog(string key, string message)
    {
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
        _marks.Dispose();
        _supervisor.Dispose();
    }
}
